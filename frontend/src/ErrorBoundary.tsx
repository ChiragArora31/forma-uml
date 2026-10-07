import { Component, type ReactNode } from 'react';

export default class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (this.state.failed)
      return (
        <main className="boot-error">
          <h1>Let’s reopen your workspace.</h1>
          <p>Your saved revisions are safe. Reopening restores the workspace and saved draft.</p>
          <button className="primary" onClick={() => location.reload()}>
            Reopen workspace
          </button>
        </main>
      );
    return this.props.children;
  }
}
