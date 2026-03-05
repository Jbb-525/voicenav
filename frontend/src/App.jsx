import { BrowserRouter, Routes, Route } from 'react-router-dom'
import ChatPage from './pages/ChatPage'
import ExecutionPage from './pages/ExecutionPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/run" element={<ExecutionPage />} />
      </Routes>
    </BrowserRouter>
  )
}
