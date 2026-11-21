#!/usr/bin/env python3
"""LoRA-distil the teacher's verified outputs into a small Qwen. Merges and saves for vLLM.
  train_student.py BASE OUT_DIR   (reads /vault/data/sft.jsonl)
"""
import json, os, sys, time, torch
from datasets import Dataset
from peft import LoraConfig
from trl import SFTConfig, SFTTrainer
from transformers import AutoTokenizer
import transformers as T

base, out = sys.argv[1], sys.argv[2]
SFT = os.environ.get("SFT", "/vault/data/sft.jsonl"); TAG = os.environ.get("TAG", "student")
rows = [json.loads(l) for l in open(SFT)]
print("sft rows", len(rows), flush=True)
tok = AutoTokenizer.from_pretrained(base)
model = None
for cls in ("AutoModelForImageTextToText", "AutoModelForCausalLM"):
    try:
        model = getattr(T, cls).from_pretrained(base, dtype=torch.bfloat16, device_map="cuda", attn_implementation="sdpa"); print("loaded", cls); break
    except Exception as e:
        print(cls, "failed:", str(e)[:200])

cfg = SFTConfig(output_dir=f"{out}-ckpt", num_train_epochs=int(os.environ.get("EPOCHS", 2)), per_device_train_batch_size=8, gradient_accumulation_steps=2,
                learning_rate=2e-4, lr_scheduler_type="cosine", warmup_steps=10, logging_steps=10, save_steps=100, save_total_limit=1,
                bf16=True, max_length=2048, report_to=[], gradient_checkpointing=True)
lora = LoraConfig(r=32, lora_alpha=64, lora_dropout=0.05, target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"], task_type="CAUSAL_LM")
t0 = time.time()
tr = SFTTrainer(model=model, args=cfg, train_dataset=Dataset.from_list(rows), processing_class=tok, peft_config=lora)
resume = any(d.startswith("checkpoint") for d in os.listdir(cfg.output_dir)) if os.path.isdir(cfg.output_dir) else False
tr.train(resume_from_checkpoint=resume or None)
merged = tr.model.merge_and_unload(); merged.save_pretrained(out, safe_serialization=True); tok.save_pretrained(out)
for f in ("preprocessor_config.json", "chat_template.jinja", "video_preprocessor_config.json"):
    try:
        from huggingface_hub import hf_hub_download; import shutil; shutil.copy(hf_hub_download(base, f), out)
    except Exception: pass
json.dump({"base": base, "rows": len(rows), "train_minutes": round((time.time() - t0) / 60, 1), "log": tr.state.log_history[-5:]},
          open(f"/vault/results/train_{TAG}.json", "w"), indent=1, default=str)
print("saved", out, flush=True)
