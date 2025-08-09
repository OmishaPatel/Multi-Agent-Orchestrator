import './style.css'

class AppState {
  constructor() {
    this.currentRequest = null;
    this.threadId = null;
    this.status = 'idle'; // idle, planning, executing, completed, error
    this.plan = null;
    this.results = {};
    this.listeners = new Set();
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  setState(updates) {
    Object.assign(this, updates);
    this.listeners.forEach(listener => listener(this));
  }
}

// DOM utilities
class DOMUtils {
  static createElement(tag, className = '', textContent = '') {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (textContent) element.textContent = textContent;
    return element;
  }

  static clearElement(element) {
    while (element.firstChild) {
      element.removeChild(element.firstChild);
    }
  }

  static show(element) {
    element.style.display = '';
  }

  static hide(element) {
    element.style.display = 'none';
  }

  static addClass(element, className) {
    element.classList.add(className);
  }

  static removeClass(element, className) {
    element.classList.remove(className);
  }

  static toggleClass(element, className) {
    element.classList.toggle(className);
  }
}

// Application initialization
class ClarityApp {
  constructor() {
    this.state = new AppState();
    this.init();
  }

  init() {
    this.setupDOM();
    this.setupEventListeners();
    this.render();
  }

  setupDOM() {
    // Create main application structure
    document.querySelector('#app').innerHTML = `
      <div class="app">
        <header class="app-header">
          <div class="container">
            <h1 class="text-2xl font-bold text-primary">Clarity.ai</h1>
            <p class="text-sm text-secondary mt-1">Multi-Agent Task Orchestration System</p>
          </div>
        </header>
        
        <main class="app-main">
          <div class="container">
            <div id="app-content" class="grid gap-6">
              <!-- Dynamic content will be rendered here -->
            </div>
          </div>
        </main>
        
        <footer class="app-footer">
          <div class="container">
            <p>&copy; 2025 Clarity.ai - Powered by Multi-Agent AI</p>
          </div>
        </footer>
      </div>
    `;

    // Cache DOM references
    this.elements = {
      content: document.getElementById('app-content'),
      header: document.querySelector('.app-header'),
      main: document.querySelector('.app-main'),
      footer: document.querySelector('.app-footer')
    };
  }

  setupEventListeners() {
    // Global error handling
    window.addEventListener('error', (event) => {
      console.error('Application error:', event.error);
      this.handleError(event.error);
    });

    // State change listener
    this.state.subscribe((newState) => {
      this.render();
    });
  }

  render() {
    // This will be expanded in future tasks to render different components
    // based on application state
    const { content } = this.elements;
    
    switch (this.state.status) {
      case 'idle':
        this.renderWelcome();
        break;
      case 'planning':
        this.renderPlanning();
        break;
      case 'executing':
        this.renderExecution();
        break;
      case 'completed':
        this.renderResults();
        break;
      case 'error':
        this.renderError();
        break;
      default:
        this.renderWelcome();
    }
  }

  renderWelcome() {
    this.elements.content.innerHTML = `
      <div class="card">
        <div class="card-header">
          <h2 class="card-title">Welcome to Clarity.ai</h2>
          <p class="card-description">
            Transform complex requests into structured plans and executed results
          </p>
        </div>
        
        <div class="text-center py-8">
          <p class="text-lg text-secondary mb-6">
            Ready to orchestrate your next multi-agent workflow
          </p>
          <button class="btn btn-primary" id="get-started-btn">
            Get Started
          </button>
        </div>
      </div>
    `;

    // Add event listener for get started button
    document.getElementById('get-started-btn').addEventListener('click', () => {
      this.state.setState({ status: 'ready' });
    });
  }

  renderPlanning() {
    this.elements.content.innerHTML = `
      <div class="card">
        <div class="card-header">
          <h2 class="card-title">Planning Phase</h2>
          <p class="card-description">AI is analyzing your request and creating an execution plan</p>
        </div>
        
        <div class="text-center py-8">
          <div class="loading mx-auto mb-4" style="width: 40px; height: 40px; position: relative;"></div>
          <p class="text-secondary">Generating intelligent task breakdown...</p>
        </div>
      </div>
    `;
  }

  renderExecution() {
    this.elements.content.innerHTML = `
      <div class="card">
        <div class="card-header">
          <h2 class="card-title">Execution Phase</h2>
          <p class="card-description">Specialized agents are working on your tasks</p>
        </div>
        
        <div class="py-6">
          <div class="grid gap-4">
            <!-- Task progress will be rendered here -->
            <div class="text-center text-secondary">
              Execution visualization will be implemented in future tasks
            </div>
          </div>
        </div>
      </div>
    `;
  }

  renderResults() {
    this.elements.content.innerHTML = `
      <div class="card">
        <div class="card-header">
          <h2 class="card-title">Results</h2>
          <p class="card-description">Your workflow has been completed successfully</p>
        </div>
        
        <div class="py-6">
          <div class="text-center text-secondary">
            Results display will be implemented in future tasks
          </div>
        </div>
      </div>
    `;
  }

  renderError() {
    this.elements.content.innerHTML = `
      <div class="card">
        <div class="card-header">
          <h2 class="card-title text-error">Error</h2>
          <p class="card-description">Something went wrong during execution</p>
        </div>
        
        <div class="py-6 text-center">
          <p class="text-secondary mb-4">Please try again or contact support</p>
          <button class="btn btn-secondary" onclick="location.reload()">
            Restart Application
          </button>
        </div>
      </div>
    `;
  }

  handleError(error) {
    console.error('Application error:', error);
    this.state.setState({ 
      status: 'error', 
      error: error.message || 'An unexpected error occurred' 
    });
  }
}

// Initialize application when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  window.clarityApp = new ClarityApp();
});

// Export for potential testing
export { ClarityApp, AppState, DOMUtils };
