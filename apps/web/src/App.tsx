import { Route, Routes } from 'react-router-dom'

function HomePage() {
  return (
    <main>
      <h1>ModelForge</h1>
      <p>Upload a model, compress or convert it, and download the result.</p>
    </main>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
    </Routes>
  )
}

export default App
