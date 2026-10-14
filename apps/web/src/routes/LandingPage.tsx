import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../ui/Button/Button'
import { Chip } from '../ui/Chip/Chip'
import { TechniqueTable } from '../features/catalog/TechniqueTable'
import { getTechniques } from '../features/catalog/types'
import styles from './LandingPage.module.css'

const FORMATS = [
  'ONNX',
  'TFLite',
  'TorchScript',
  'SavedModel',
  'safetensors',
  'GGUF',
  'OpenVINO',
  'TensorRT',
  'Core ML',
]

const STEPS = [
  { title: 'Upload', body: 'Drop a model file or point us at a Hugging Face repo.' },
  { title: 'Pick a method', body: 'Choose a compression technique or a target format.' },
  { title: 'Download', body: 'Watch progress live and download the result when it is ready.' },
]

export function LandingPage() {
  const navigate = useNavigate()
  const techniques = getTechniques()
  const [selectedTechnique, setSelectedTechnique] = useState(techniques[0]?.id ?? '')

  return (
    <>
      <section className={styles.hero}>
        <h1 className={styles.heroTitle}>Compress and convert any model, in minutes.</h1>
        <p className={styles.heroSubtitle}>
          Upload a model or import from Hugging Face. Quantize, prune, distill, or convert it to
          the format your runtime needs — see the accuracy trade-off before you commit.
        </p>
        <div className={styles.heroActions}>
          <Button onClick={() => navigate('/signup')}>Get started</Button>
          <Button variant="secondary" onClick={() => navigate('/app')}>
            Try it now
          </Button>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Compare techniques</h2>
        <TechniqueTable
          techniques={techniques}
          value={selectedTechnique}
          onChange={setSelectedTechnique}
        />
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Supported formats</h2>
        <div className={styles.formats}>
          {FORMATS.map((format) => (
            <Chip key={format} disabled>
              {format}
            </Chip>
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>How it works</h2>
        <div className={styles.steps}>
          {STEPS.map((step, index) => (
            <div key={step.title} className={styles.step}>
              <span className={styles.stepNumber}>{index + 1}</span>
              <h3>{step.title}</h3>
              <p>{step.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.cta}>
        <Button onClick={() => navigate('/signup')}>Start compressing for free</Button>
      </section>
    </>
  )
}
