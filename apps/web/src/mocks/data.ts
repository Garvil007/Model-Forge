import { SAMPLE_MODELS } from '../features/model/sampleModels'

export { SAMPLE_MODELS }

export interface HfRepoFixture {
  repoId: string
  gated: boolean
  model: typeof SAMPLE_MODELS.resnet
}

/** Known repo ids the mock `POST /api/models/import-hf` recognizes. Anything else 404s;
 * `meta-llama/Llama-3.2-1B` is gated and requires `token` to be set. */
export const HF_REPOS: HfRepoFixture[] = [
  { repoId: 'microsoft/resnet-50', gated: false, model: SAMPLE_MODELS.resnet },
  { repoId: 'meta-llama/Llama-3.2-1B', gated: true, model: SAMPLE_MODELS.llama },
  { repoId: 'Ultralytics/YOLOv8', gated: false, model: SAMPLE_MODELS.yolo },
]
