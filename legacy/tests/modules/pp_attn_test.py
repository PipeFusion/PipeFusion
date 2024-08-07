import unittest
import torch
from diffusers.models.attention import Attention
from legacy.pipefuser.modules.dit.patch_parallel.attn import DistriSelfAttentionPP
from legacy.pipefuser.utils import DistriConfig
import os


class TestDistriSelfAttentionPP(unittest.TestCase):
    def setUp(self):
        self.hidden_dim = 64
        self.height = 4
        self.width = 4
        self.sequence_length = 128
        self.dtype = torch.bfloat16

        # Set device using rank
        rank = int(os.environ.get("LOCAL_RANK", 0))
        self.device = f"cuda:{rank}"

        self.attention = (
            Attention(query_dim=self.hidden_dim).to(self.dtype).to(self.device)
        )
        self.distri_config = DistriConfig(
            height=self.height, width=self.width, parallelism="sequence"
        )

        self.distri_config.use_seq_parallel_attn = True
        self.attention_pp_true = DistriSelfAttentionPP(
            self.attention, self.distri_config
        )

        self.distri_config.use_seq_parallel_attn = False
        self.attention_pp_false = DistriSelfAttentionPP(
            self.attention, self.distri_config
        )

        self.hidden_states = torch.rand(
            1,
            self.sequence_length,
            self.hidden_dim,
            dtype=self.dtype,
            device=self.device,
        )

    def test_flash_attn_true_vs_false(self):
        output_true = self.attention_pp_true(self.hidden_states)
        output_false = self.attention_pp_false(self.hidden_states)

        self.assertTrue(torch.allclose(output_true, output_false))

    def tearDown(self):
        del self.attention_pp_true
        del self.attention_pp_false
        del self.hidden_states


if __name__ == "__main__":
    unittest.main()
