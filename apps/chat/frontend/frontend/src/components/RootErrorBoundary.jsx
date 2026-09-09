import { Component } from 'react'

export class RootErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 32, textAlign: 'center' }}>
          <h2>页面出错了</h2>
          <p style={{ color: '#c00' }}>请刷新页面后重试。若问题持续，请联系支持。</p>
          <button onClick={() => window.location.reload()}>刷新页面</button>
        </div>
      )
    }
    return this.props.children
  }
}
