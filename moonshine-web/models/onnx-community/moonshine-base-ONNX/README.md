---
license: mit
base_model:
- UsefulSensors/moonshine-base
library_name: transformers.js
pipeline_tag: automatic-speech-recognition
---


## Usage

### Transformers.js

If you haven't already, you can install the [Transformers.js](https://huggingface.co/docs/transformers.js) JavaScript library from [NPM](https://www.npmjs.com/package/@huggingface/transformers) using:
```bash
npm i @huggingface/transformers
```

**Example:** Automatic speech recognition w/ Moonshine base.
```js
import { pipeline } from "@huggingface/transformers";

const transcriber = await pipeline("automatic-speech-recognition", "onnx-community/moonshine-base-ONNX");
const output = await transcriber("https://huggingface.co/datasets/Xenova/transformers.js-docs/resolve/main/jfk.wav");
console.log(output);
// { text: 'And so my fellow Americans ask not what your country can do for you as what you can do for your country.' }
```

### ONNXRuntime

```py
import numpy as np
import onnxruntime as ort
from transformers import AutoConfig, AutoTokenizer
import librosa

# Load config and tokenizer
model_id = 'onnx-community/moonshine-base-ONNX'
config = AutoConfig.from_pretrained(model_id)
tokenizer = AutoTokenizer.from_pretrained(model_id)

# Load encoder and decoder sessions
encoder_session = ort.InferenceSession('./onnx/encoder_model_quantized.onnx')
decoder_session = ort.InferenceSession('./onnx/decoder_model_merged_quantized.onnx')

# Set config values
eos_token_id = config.eos_token_id
num_key_value_heads = config.decoder_num_key_value_heads
dim_kv = config.hidden_size // config.decoder_num_attention_heads

# Load audio
audio_file = 'jfk.wav'
audio = librosa.load(audio_file, sr=16_000)[0][None]

# Run encoder
encoder_outputs = encoder_session.run(None, dict(input_values=audio))[0]

# Prepare decoder inputs
batch_size = encoder_outputs.shape[0]
input_ids = np.array([[config.decoder_start_token_id]] * batch_size)
past_key_values = {
    f'past_key_values.{layer}.{module}.{kv}': np.zeros([batch_size, num_key_value_heads, 0, dim_kv], dtype=np.float32)
    for layer in range(config.decoder_num_hidden_layers)
    for module in ('decoder', 'encoder')
    for kv in ('key', 'value')
}

# max 6 tokens per second of audio
max_len = min((audio.shape[-1] // 16_000) * 6, config.max_position_embeddings)

generated_tokens = input_ids
for i in range(max_len):
  use_cache_branch = i > 0
  logits, *present_key_values = decoder_session.run(None, dict(
      input_ids=generated_tokens[:, -1:],
      encoder_hidden_states=encoder_outputs,
      use_cache_branch=[use_cache_branch],
      **past_key_values,
  ))
  next_tokens = logits[:, -1].argmax(-1, keepdims=True)
  for j, key in enumerate(past_key_values):
    if not use_cache_branch or 'decoder' in key:
      past_key_values[key] = present_key_values[j]
  generated_tokens = np.concatenate([generated_tokens, next_tokens], axis=-1)
  if (next_tokens == eos_token_id).all():
    break

result = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)
print(result)
```
