/** Display names for model formats — mirrors packages/catalog/src/modelforge_catalog/formats.py's
 * FORMAT dict exactly (docs/ui-prototype.html's FORMAT object). Not part of catalog.json since
 * it's a display concern, not operation data. */
export const FORMAT_LABELS: Record<string, string> = {
  onnx: 'ONNX',
  tflite: 'TensorFlow Lite',
  keras: 'Keras',
  torch: 'PyTorch',
  torchscript: 'TorchScript',
  safetensors: 'safetensors',
  yolo: 'YOLO (Ultralytics)',
  gguf: 'GGUF',
  openvino: 'OpenVINO IR',
  tensorrt: 'TensorRT engine',
  coreml: 'Core ML',
  savedmodel: 'TensorFlow SavedModel',
}

export function formatLabel(format: string): string {
  return FORMAT_LABELS[format] ?? format
}
