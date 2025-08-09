import './style.css'
import './components/InputForm/input-form.css'
import './components/ExecutionFlow/execution-flow.css'
import './components/PlanVerification/PlanVerification.css'
import { InputForm } from './components/InputForm/InputForm.js'
import { ExecutionFlow } from './components/ExecutionFlow/ExecutionFlow.js'
import { PlanVerification } from './components/PlanVerification/PlanVerification.js'
import { apiClient, StatusPoller } from './utils/api.js'
import { DOMUtils } from './utils/dom.js'

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



// Application initialization
class ClarityApp {
  constructor() {
    this.state = new AppState();
    this.statusPoller = null;
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

    // Cleanup polling when page unloads
    window.addEventListener('beforeunload', () => {
      this.stopPolling();
    });
  }

  render() {
    // This will be expanded in future tasks to render different components
    // based on application state
    const { content } = this.elements;

    switch (this.state.status) {
      case 'idle':
      case 'ready':
        this.renderWelcome();
        break;
      case 'planning':
        this.renderPlanning();
        break;
      case 'awaiting_approval':
        this.renderApproval();
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
    // Stop any polling when returning to welcome
    this.stopPolling();

    // Clear existing content
    DOMUtils.clearElement(this.elements.content);

    // Cleanup other components
    if (this.executionFlow) {
      this.executionFlow.destroy();
      this.executionFlow = null;
    }
    if (this.planVerification) {
      this.planVerification.reset();
      this.planVerification = null;
    }

    // Create and render InputForm component
    if (!this.inputForm) {
      this.inputForm = new InputForm(this.state, apiClient);
    }

    this.elements.content.appendChild(this.inputForm.render());
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
          <div class="mt-4">
            <small class="text-secondary">Thread ID: ${this.state.threadId || 'Not available'}</small>
          </div>
        </div>

        <!-- Temporary debug controls -->
        <div class="text-center mt-4" style="border-top: 1px solid var(--color-border); padding-top: var(--space-4);">
          <p class="text-xs text-secondary mb-2">Debug Controls (Development Only)</p>
          <button class="btn btn-secondary btn-sm" id="debug-execution">
            Skip to Execution View
          </button>
          <button class="btn btn-secondary btn-sm ml-2" id="debug-status">
            Check Status
          </button>
        </div>
      </div>
    `;

    // Add debug event listeners
    const debugExecutionBtn = this.elements.content.querySelector('#debug-execution');
    const debugStatusBtn = this.elements.content.querySelector('#debug-status');

    debugExecutionBtn?.addEventListener('click', () => {
      console.log('Debug: Manually transitioning to execution state');
      this.state.setState({
        status: 'executing',
        plan: [
          {
            id: 1,
            type: 'research',
            description: 'Sample research task for testing',
            dependencies: [],
            status: 'completed',
            result: 'Research completed successfully'
          },
          {
            id: 2,
            type: 'code',
            description: 'Sample code generation task',
            dependencies: [1],
            status: 'in_progress',
            result: null
          },
          {
            id: 3,
            type: 'analysis',
            description: 'Sample analysis task',
            dependencies: [1, 2],
            status: 'pending',
            result: null
          }
        ],
        progress: 0.4
      });
    });

    debugStatusBtn?.addEventListener('click', async () => {
      console.log('Debug: Checking status manually');
      if (this.state.threadId) {
        try {
          const status = await apiClient.getStatus(this.state.threadId);
          console.log('Status response:', status);
          alert(`Status: ${JSON.stringify(status, null, 2)}`);
        } catch (error) {
          console.error('Status check failed:', error);
          alert(`Error: ${error.message}`);
        }
      } else {
        alert('No thread ID available');
      }
    });

    // Start polling for status updates during planning phase
    this.startPlanningPolling();
  }

  renderExecution() {
    // Clear existing content
    DOMUtils.clearElement(this.elements.content);

    // Cleanup other components
    if (this.inputForm) {
      this.inputForm.destroy();
      this.inputForm = null;
    }
    if (this.planVerification) {
      this.planVerification.reset();
      this.planVerification = null;
    }

    // Create and render ExecutionFlow component
    if (!this.executionFlow) {
      this.executionFlow = new ExecutionFlow(this.state, apiClient);
    }

    this.elements.content.appendChild(this.executionFlow.render());
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

  /**
   * Start polling during planning phase to detect when execution begins
   */
  startPlanningPolling() {
    if (!this.state.threadId) {
      console.warn('No thread ID available for polling');
      return;
    }

    // Stop any existing polling
    this.stopPolling();

    this.statusPoller = new StatusPoller(
      apiClient,
      this.state.threadId,
      (statusData) => this.handleStatusUpdate(statusData),
      {
        interval: 5000, // Reduced from 2000ms to 5000ms (5 seconds)
        maxAttempts: 60, // Reduced max attempts
        backoffMultiplier: 1.2, // Slightly more aggressive backoff
        maxInterval: 15000 // Increased max interval to 15 seconds
      }
    );

    this.statusPoller.start();
  }

  /**
   * Stop any active polling
   */
  stopPolling() {
    if (this.statusPoller) {
      this.statusPoller.stop();
      this.statusPoller = null;
    }
  }

  /**
   * Handle status updates from polling
   */
  handleStatusUpdate(statusData) {
    if (!statusData.success) {
      console.error('Status polling failed:', statusData.error);
      return;
    }

    console.log('Status update received:', statusData);

    // Update application state based on backend status
    const updates = {
      progress: statusData.progress || 0
    };

    // Handle status transitions
    switch (statusData.status) {
      case 'planning':
        updates.status = 'planning';
        break;
      case 'pending_approval':
      case 'awaiting_approval':
        updates.status = 'awaiting_approval'; // New state for approval
        updates.plan = statusData.plan;
        // Slow down polling when waiting for approval
        if (this.statusPoller) {
          this.statusPoller.options.interval = 10000; // 10 seconds
        }
        break;
      case 'executing':
        updates.status = 'executing';
        updates.plan = statusData.plan;
        break;
      case 'completed':
        updates.status = 'completed';
        updates.results = statusData.results;
        this.stopPolling();
        break;
      case 'failed':
        updates.status = 'error';
        updates.error = statusData.error || 'Workflow execution failed';
        this.stopPolling();
        break;
      case 'cancelled':
        updates.status = 'error';
        updates.error = 'Workflow was cancelled';
        this.stopPolling();
        break;
    }

    this.state.setState(updates);
  }

  /**
   * Render approval phase where user can approve or reject the plan
   */
  renderApproval() {
    // Clear existing content
    DOMUtils.clearElement(this.elements.content);

    // Cleanup other components
    if (this.inputForm) {
      this.inputForm.destroy();
      this.inputForm = null;
    }
    if (this.executionFlow) {
      this.executionFlow.destroy();
      this.executionFlow = null;
    }

    // Create container for PlanVerification component
    const planVerificationContainer = document.createElement('div');
    this.elements.content.appendChild(planVerificationContainer);

    // Create and initialize PlanVerification component
    if (!this.planVerification) {
      this.planVerification = new PlanVerification(planVerificationContainer);

      // Listen for plan approval events
      document.addEventListener('stateUpdate', (e) => {
        if (e.detail.type === 'planApproval') {
          this.handlePlanApproval(e.detail);
        }
      });
    }

    // Display the current plan
    if (this.state.plan && this.state.threadId) {
      // Trigger plan display through custom event
      document.dispatchEvent(new CustomEvent('stateUpdate', {
        detail: {
          type: 'planReceived',
          plan: this.state.plan,
          threadId: this.state.threadId
        }
      }));
    }
  }

  /**
   * Handle plan approval events from PlanVerification component
   */
  handlePlanApproval(approvalData) {
    const { approved, feedback, threadId } = approvalData;

    console.log('Plan approval received:', { approved, feedback, threadId });

    if (approved) {
      // Plan was approved, continue polling to see execution start
      console.log('Plan approved, waiting for execution to begin');
      // The status polling will automatically detect the transition to executing
    } else {
      // Plan was rejected with feedback, return to planning state
      console.log('Plan rejected, returning to planning phase');
      this.state.setState({
        status: 'planning',
        plan: null // Clear the rejected plan
      });
    }
  }
}

// Initialize application when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  window.clarityApp = new ClarityApp();
});

// Export for potential testing
export { ClarityApp, AppState };
