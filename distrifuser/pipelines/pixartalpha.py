# Adapted from
# https://github.com/huggingface/diffusers/blob/v0.27.2/src/diffusers/pipelines/pixart_alpha/pipeline_pixart_alpha.py#L218

import torch
from diffusers import PixArtAlphaPipeline
from diffusers.models.transformers.transformer_2d import Transformer2DModel

# from distrifuser.models.distri_sdxl_unet_tp import DistriSDXLUNetTP
from distrifuser.models import NaivePatchDiT, DistriDiTPP
from distrifuser.utils import DistriConfig, PatchParallelismCommManager
from distrifuser.logger import init_logger

logger = init_logger(__name__)

class DistriPixArtAlphaPipeline:
    def __init__(self, pipeline: PixArtAlphaPipeline, module_config: DistriConfig):
        self.pipeline = pipeline

        # assert module_config.do_classifier_free_guidance == False
        assert module_config.split_batch == False

        self.distri_config = module_config

        self.static_inputs = None

        self.prepare()

    @staticmethod
    def from_pretrained(distri_config: DistriConfig, **kwargs):
        device = distri_config.device
        pretrained_model_name_or_path = kwargs.pop(
            "pretrained_model_name_or_path", "PixArt-alpha/PixArt-XL-2-1024-MS"
        )
        torch_dtype = kwargs.pop("torch_dtype", torch.float16)
        transformer = Transformer2DModel.from_pretrained(
            pretrained_model_name_or_path, torch_dtype=torch_dtype, subfolder="transformer"
        ).to(device)

        if distri_config.parallelism == "patch":
            transformer = DistriDiTPP(transformer, distri_config)
        elif distri_config.parallelism == "naive_patch":
            logger.info("Using naive patch parallelism")
            transformer = NaivePatchDiT(transformer, distri_config)
        else:
            raise ValueError(f"Unknown parallelism: {distri_config.parallelism}")

        pipeline = PixArtAlphaPipeline.from_pretrained(
            pretrained_model_name_or_path, torch_dtype=torch_dtype, transformer=transformer, **kwargs
        ).to(device)
        return DistriPixArtAlphaPipeline(pipeline, distri_config)

    def set_progress_bar_config(self, **kwargs):
        pass

    @torch.no_grad()
    def __call__(self, prompt, *args, **kwargs):
        self.pipeline.transformer.set_counter(0)
        return self.pipeline(prompt=prompt, *args, **kwargs)

    @torch.no_grad()
    def prepare(self, **kwargs):
        distri_config = self.distri_config

        static_inputs = {}
        static_outputs = []
        cuda_graphs = []
        pipeline = self.pipeline

        height = distri_config.height
        width = distri_config.width
        assert height % 8 == 0 and width % 8 == 0

        device = distri_config.device

        batch_size = distri_config.batch_size or 1
        num_images_per_prompt = 1
        # 3. Encode input prompt
        (
            prompt_embeds,
            prompt_attention_mask,
            negative_prompt_embeds,
            negative_prompt_attention_mask,
        ) = self.pipeline.encode_prompt(
            prompt="",
            do_classifier_free_guidance=distri_config.do_classifier_free_guidance,
            device=device,
        )

        if distri_config.do_classifier_free_guidance:
            prompt_embeds = torch.cat([negative_prompt_embeds, prompt_embeds], dim=0)
            prompt_attention_mask = torch.cat([negative_prompt_attention_mask, prompt_attention_mask], dim=0)

        # 7. Prepare added time ids & embeddings

        t = torch.zeros([2], device=device, dtype=torch.long)

        guidance_scale = 4.0
        latent_size = pipeline.transformer.config.sample_size
        latent_channels = pipeline.transformer.config.in_channels
        latents = torch.zeros(
            [batch_size, latent_channels, latent_size, latent_size],
            device=device,
            dtype=pipeline.transformer.dtype,
        )
        latent_model_input = torch.cat([latents, latents], 0) if guidance_scale > 1 else latents

        # encoder_hidden_states.shape torch.Size([2, 120, 4096])
        # encoder_attention_mask.shape torch.Size([2, 120])
        # resolution.shape torch.Size([2, 2])
        # aspect_ratio.shape torch.Size([2, 1])
        static_inputs["hidden_states"] = latent_model_input
        static_inputs["timestep"] = t
        static_inputs["encoder_hidden_states"] = prompt_embeds
        static_inputs["encoder_attention_mask"] = prompt_attention_mask
        added_cond_kwargs = {"resolution": None, "aspect_ratio": None}
        if pipeline.transformer.config.sample_size == 128:
            resolution = torch.tensor([0, 0]).repeat(batch_size * num_images_per_prompt, 1)
            aspect_ratio = torch.tensor([0.0]).repeat(batch_size * num_images_per_prompt, 1)
            resolution = resolution.to(dtype=prompt_embeds.dtype, device=device)
            aspect_ratio = aspect_ratio.to(dtype=prompt_embeds.dtype, device=device)

            if distri_config.do_classifier_free_guidance:
                resolution = torch.cat([resolution, resolution], dim=0)
                aspect_ratio = torch.cat([aspect_ratio, aspect_ratio], dim=0)

            added_cond_kwargs = {"resolution": resolution, "aspect_ratio": aspect_ratio}
        static_inputs["added_cond_kwargs"] = added_cond_kwargs

        # Used to create communication buffer
        comm_manager = None
        if distri_config.n_device_per_batch > 1:
            comm_manager = PatchParallelismCommManager(distri_config)
            pipeline.transformer.set_comm_manager(comm_manager)

            # Only used for creating the communication buffer
            pipeline.transformer.set_counter(0)
            pipeline.transformer(**static_inputs, return_dict=False, record=True)
            if comm_manager.numel > 0:
                comm_manager.create_buffer()

        # Pre-run
        pipeline.transformer.set_counter(0)
        pipeline.transformer(**static_inputs, return_dict=False, record=True)

        if distri_config.use_cuda_graph:
            if comm_manager is not None:
                comm_manager.clear()
            if distri_config.parallelism == "naive_patch":
                counters = [0, 1]
            elif distri_config.parallelism == "patch":
                counters = [0, distri_config.warmup_steps + 1, distri_config.warmup_steps + 2]
            else:
                raise ValueError(f"Unknown parallelism: {distri_config.parallelism}")
            for counter in counters:
                graph = torch.cuda.CUDAGraph()
                with torch.cuda.graph(graph):
                    pipeline.transformer.set_counter(counter)
                    output = pipeline.transformer(**static_inputs, return_dict=False, record=True)[0]
                    static_outputs.append(output)
                cuda_graphs.append(graph)
            pipeline.transformer.setup_cuda_graph(static_outputs, cuda_graphs)

        self.static_inputs = static_inputs