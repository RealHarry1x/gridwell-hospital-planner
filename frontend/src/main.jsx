import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';

class ErrorBoundary extends React.Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error }; }
  render() {
    if (this.state.error) return <main className="fatal"><h1>The workspace could not render.</h1><p>{this.state.error.message}</p><button onClick={() => window.location.reload()}>Reload workspace</button><p>The Python backend keeps saved plans and presets.</p></main>;
    return this.props.children;
  }
}

createRoot(document.getElementById('root')).render(<ErrorBoundary><App/></ErrorBoundary>);
