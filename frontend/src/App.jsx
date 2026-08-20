import ChatWidget from './components/Chat/ChatWidget'
import { ChatProvider } from './context/ChatContext'
import './App.css'

function App() {
  return (
    <ChatProvider>
      <div className="app-backdrop">
        <h1>Rasa Café</h1>
        <p>Click the chat bubble in the corner to talk to Rumi, our virtual assistant.</p>
      </div>
      <ChatWidget />
    </ChatProvider>
  )
}

export default App
