torchrun --nproc_per_node=1 scripts/run.py --test_times 50 --mode benchmark --pipeline pixartalpha
torchrun --nproc_per_node=2 scripts/run.py --test_times 50 --mode benchmark --pipeline pixartalpha
torchrun --nproc_per_node=4 scripts/run.py --test_times 50 --mode benchmark --pipeline pixartalpha
torchrun --nproc_per_node=2 scripts/run.py --test_times 50 --mode benchmark --pipeline pixartalpha --parallelism naive_patch
torchrun --nproc_per_node=4 scripts/run.py --test_times 50 --mode benchmark --pipeline pixartalpha --parallelism naive_patch
torchrun --nproc_per_node=1 scripts/run.py --test_times 50 --mode benchmark --pipeline dit --model_path facebook/DiT-XL-2-512
torchrun --nproc_per_node=2 scripts/run.py --test_times 50 --mode benchmark --pipeline dit --model_path facebook/DiT-XL-2-512
torchrun --nproc_per_node=4 scripts/run.py --test_times 50 --mode benchmark --pipeline dit --model_path facebook/DiT-XL-2-512
torchrun --nproc_per_node=2 scripts/run.py --test_times 50 --mode benchmark --pipeline dit --model_path facebook/DiT-XL-2-512 --parallelism naive_patch 
torchrun --nproc_per_node=4 scripts/run.py --test_times 50 --mode benchmark --pipeline dit --model_path facebook/DiT-XL-2-512 --parallelism naive_patch
torchrun --nproc_per_node=1 scripts/run.py --test_times 50 --mode benchmark --pipeline dit --model_path facebook/DiT-XL-2-256
torchrun --nproc_per_node=2 scripts/run.py --test_times 50 --mode benchmark --pipeline dit --model_path facebook/DiT-XL-2-256
torchrun --nproc_per_node=4 scripts/run.py --test_times 50 --mode benchmark --pipeline dit --model_path facebook/DiT-XL-2-256