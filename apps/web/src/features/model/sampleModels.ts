import type { DetectedModel, SampleKey } from './types'

/** Port of `docs/ui-prototype.html`'s `SAMPLES` object (lines 492-501) — the "Or try a sample"
 * buttons. `src/mocks/data.ts` reuses these so the mock `import-hf`/sample flow and this feature
 * never drift apart. */
export const SAMPLE_MODELS: Record<SampleKey, DetectedModel> = {
  resnet: {
    filename: 'resnet50.onnx',
    format: 'onnx',
    family: 'vision',
    bits: 32,
    params: 25.6e6,
    size: 102_442_450,
    inputs: 'input [batch, 3, 224, 224]',
    metric: ['Top-1 accuracy (ImageNet val)', 76.1, '%'],
  },
  llama: {
    filename: 'Llama-3.2-1B/model.safetensors',
    format: 'safetensors',
    family: 'llm',
    bits: 16,
    params: 1.236e9,
    size: 2_471_645_608,
    inputs: 'input_ids [batch, sequence]',
    metric: ['Perplexity (WikiText-2)', 9.75, ''],
  },
  yolo: {
    filename: 'yolov8n.pt',
    format: 'yolo',
    family: 'vision',
    bits: 32,
    params: 3.2e6,
    size: 6_549_796,
    inputs: 'images [batch, 3, 640, 640]',
    metric: ['mAP50-95 (COCO val)', 37.3, '%'],
  },
  mobilenet: {
    filename: 'mobilenet_v2.keras',
    format: 'keras',
    family: 'vision',
    bits: 32,
    params: 3.5e6,
    size: 14_536_120,
    inputs: 'input [batch, 224, 224, 3]',
    metric: ['Top-1 accuracy (ImageNet val)', 71.8, '%'],
  },
}

export const SAMPLE_LABELS: Record<SampleKey, string> = {
  resnet: 'ResNet-50 (ONNX)',
  llama: 'Llama 3.2 1B (safetensors)',
  yolo: 'YOLOv8n (PyTorch)',
  mobilenet: 'MobileNetV2 (Keras)',
}
