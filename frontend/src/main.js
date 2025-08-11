import './style.css'
import './components/InputForm/input-form.css'
import './components/ExecutionFlow/execution-flow.css'
import './components/PlanVerification/PlanVerification.css'
import './components/FinalResult/final-result.css'
import './components/TaskCard/task-card.css'
import { InputForm } from './components/InputForm/InputForm.js'
import { ExecutionFlow } from './components/ExecutionFlow/ExecutionFlow.js'
import { PlanVerification } from './components/PlanVerification/PlanVerification.js'
import { DOMUtils } from './utils/dom.js'
import { stateManager, eventBus } from './utils/state.js'
import { apiService } from './services/apiService.js'



// Application initialization
class ClarityApp {
  constructor() {
    this.stateManager = stateManager;
    this.eventBus = eventBus;
    this.apiService = apiService;
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

    // State change listener - render on any state change
    this.stateManager.subscribe(() => {
      this.render();
    });

    // Listen for specific events
    this.eventBus.on('requestSubmitted', (data) => {
      console.log('Request submitted:', data);
    });

    this.eventBus.on('statusUpdate', (data) => {
      console.log('Status update:', data);
    });

    this.eventBus.on('apiError', (data) => {
      console.error('API error:', data);
      this.handleApiError(data);
    });

    this.eventBus.on('workflowCancelled', (data) => {
      console.log('Workflow cancelled:', data);
    });

    this.eventBus.on('approvalSubmitted', (data) => {
      console.log('Approval submitted:', data);
    });

    // Cleanup when page unloads
    window.addEventListener('beforeunload', () => {
      this.apiService.destroy();
    });
  }

  render() {
    const currentState = this.stateManager.getState();
    console.log('[ClarityApp] Rendering with status:', currentState.status, 'threadId:', currentState.threadId);

    switch (currentState.status) {
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
    // Clear existing content
    DOMUtils.clearElement(this.elements.content);

    // Cleanup other components
    this.cleanupComponents(['executionFlow', 'planVerification']);

    // Create and render InputForm component
    if (!this.inputForm) {
      this.inputForm = new InputForm(this.stateManager, this.apiService);
    }

    this.elements.content.appendChild(this.inputForm.render());
  }

  renderPlanning() {
    const currentState = this.stateManager.getState();

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
            <small class="text-secondary">Thread ID: ${currentState.threadId || 'Not available'}</small>
          </div>
          ${currentState.apiConnected ? '' : '<p class="text-error mt-2">⚠️ Connection issues detected</p>'}
        </div>

        <!-- Debug controls for development -->
        <div class="text-center mt-4" style="border-top: 1px solid var(--color-border); padding-top: var(--space-4);">
          <p class="text-xs text-secondary mb-2">Debug Controls (Development Only)</p>
          <button class="btn btn-secondary btn-sm" id="debug-execution">
            Skip to Execution View
          </button>
          <button class="btn btn-secondary btn-sm ml-2" id="debug-status">
            Check Status
          </button>
          <button class="btn btn-secondary btn-sm ml-2" id="debug-approval">
            Skip to Approval
          </button>
          <button class="btn btn-secondary btn-sm ml-2" id="debug-results">
            Skip to Results
          </button>
        </div>
      </div>
    `;

    // Add debug event listeners
    const debugExecutionBtn = this.elements.content.querySelector('#debug-execution');
    const debugStatusBtn = this.elements.content.querySelector('#debug-status');
    const debugApprovalBtn = this.elements.content.querySelector('#debug-approval');
    const debugResultsBtn = this.elements.content.querySelector('#debug-results');

    debugExecutionBtn?.addEventListener('click', () => {
      console.log('Debug: Manually transitioning to execution state');
      this.stateManager.setState({
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
      }, 'debug.execution');
    });

    debugApprovalBtn?.addEventListener('click', () => {
      console.log('Debug: Manually transitioning to approval state');
      this.stateManager.setState({
        status: 'awaiting_approval',
        plan: [
          {
            id: 1,
            type: 'research',
            description: 'Research latest developments in AI agent orchestration',
            dependencies: [],
            status: 'pending'
          },
          {
            id: 2,
            type: 'code',
            description: 'Implement multi-agent coordination system',
            dependencies: [1],
            status: 'pending'
          }
        ]
      }, 'debug.approval');
    });

    debugStatusBtn?.addEventListener('click', async () => {
      console.log('Debug: Checking status manually');
      const state = this.stateManager.getState();
      if (state.threadId) {
        try {
          const status = await this.apiService.apiClient.getStatus(state.threadId);
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

    debugResultsBtn?.addEventListener('click', () => {
      console.log('Debug: Manually transitioning to results state');
      this.stateManager.setState({
        status: 'completed',
        finalReport: `# Clarity.ai Task Execution Report
**Original Request:** Research the latest developments in artificial intelligence, analyze the impact on job markets, and create a comprehensive report
**Execution Date:** 2025-08-10 15:49:07

## Summary
- **Total Tasks:** 4
- **Completed:** 4
- **Failed:** 0

## Detailed Results

### ✅ Task 1: Research the latest developments in artificial intelligence
**Type:** research
**Status:** completed
**Result:**
Recent developments in artificial intelligence (AI) and machine learning (ML) have been significant, with advancements transforming various industries and sectors.

**Source Credibility Assessment:**
- High credibility sources: 10
- Medium credibility sources: 0
- Low credibility sources: 0
- Total sources analyzed: 10
- Enhanced Tavily sources: 9

### ✅ Task 2: Analyze the impact of artificial intelligence on job markets
**Type:** analysis
**Status:** completed
**Result:**
The impact of artificial intelligence (AI) on job markets is a topic of significant interest and concern, as evidenced by the plethora of information available from high credibility sources.

According to the Bureau of Labor Statistics (BLS), AI is expected to have a profound impact on various occupations over the next decade. The BLS projects that certain sectors, such as finance and legal services, are already experiencing the effects of AI, leading to a restructuring of job roles and responsibilities.

Research from Forbes indicates that certain sectors, such as finance and legal services, are already experiencing the effects of AI, leading to a restructuring of job roles and responsibilities.

A report from Nexford University predicts that around a quarter of all jobs in the U.S. and Europe could potentially be performed entirely by AI in the near future.

Despite these potential benefits, concerns remain about the overall impact of AI on employment. Research published in the Harvard Gazette suggests that while AI may create new opportunities, it could also lead to significant job displacement in certain sectors.

In conclusion, the impact of AI on job markets is multifaceted, with both opportunities and challenges arising from increased AI integration. While AI has the potential to enhance productivity and create new job categories, it also poses risks of job displacement and requires careful consideration of retraining and reskilling initiatives.`,
        plan: [
          {
            id: 1,
            type: 'research',
            description: 'Research the latest developments in artificial intelligence',
            status: 'completed'
          },
          {
            id: 2,
            type: 'analysis',
            description: 'Analyze the impact of artificial intelligence on job markets',
            status: 'completed'
          },
          {
            id: 3,
            type: 'synthesis',
            description: 'Create comprehensive report with findings',
            status: 'completed'
          },
          {
            id: 4,
            type: 'review',
            description: 'Review and finalize the report',
            status: 'completed'
          }
        ],
        startTime: new Date(Date.now() - 300000).toISOString() // 5 minutes ago
      }, 'debug.results');
    });
  }

  renderExecution() {
    console.log('[ClarityApp] Rendering execution view');

    // Clear existing content
    DOMUtils.clearElement(this.elements.content);

    // Cleanup other components
    this.cleanupComponents(['inputForm', 'planVerification']);

    // Create and render ExecutionFlow component
    if (!this.executionFlow) {
      console.log('[ClarityApp] Creating new ExecutionFlow component');
      this.executionFlow = new ExecutionFlow(this.stateManager, this.apiService);
    }

    const executionElement = this.executionFlow.render();
    this.elements.content.appendChild(executionElement);

    console.log('[ClarityApp] ExecutionFlow component rendered and added to DOM');
  }

  renderResults() {
    const currentState = this.stateManager.getState();
    console.log('[ClarityApp] Rendering results with state:', currentState);

    // Clear existing content
    DOMUtils.clearElement(this.elements.content);

    // Cleanup other components
    this.cleanupComponents(['inputForm', 'executionFlow', 'planVerification']);

    // Import and use FinalResult component
    import('./components/FinalResult/FinalResult.js').then(({ FinalResult }) => {
      // Create container for FinalResult
      const resultsContainer = document.createElement('div');
      resultsContainer.className = 'results-container';
      this.elements.content.appendChild(resultsContainer);

      // Prepare result data for FinalResult component
      const resultData = {
        final_report: currentState.finalReport || currentState.result || 'No final report available',
        content: currentState.finalReport || currentState.result || 'No content available',
        completed_at: new Date().toISOString(),
        started_at: currentState.startTime || new Date(Date.now() - 120000).toISOString(),
        total_tasks: currentState.plan ? currentState.plan.length : 0,
        status: 'completed'
      };

      console.log('[ClarityApp] Creating FinalResult with data:', resultData);

      // Create and render FinalResult component
      this.finalResult = new FinalResult(resultsContainer, resultData, {
        enableExport: true,
        enableSharing: true,
        showMetadata: true
      });

      // Add a "Start New Request" button after the results
      const newRequestButton = document.createElement('div');
      newRequestButton.className = 'text-center mt-6';
      newRequestButton.innerHTML = `
        <button class="btn btn-primary" id="new-request-btn">
          Start New Request
        </button>
      `;
      resultsContainer.appendChild(newRequestButton);

      // Add event listener for new request button
      newRequestButton.querySelector('#new-request-btn').addEventListener('click', () => {
        this.resetToIdle();
      });

    }).catch(error => {
      console.error('Failed to load FinalResult component:', error);

      // Fallback to simple HTML if component fails to load
      this.elements.content.innerHTML = `
        <div class="card">
          <div class="card-header">
            <h2 class="card-title">Results</h2>
            <p class="card-description">Your workflow has been completed successfully</p>
          </div>
          
          <div class="py-6">
            <div class="text-center">
              <p class="text-secondary mb-4">Final report and results:</p>
              ${currentState.finalReport ? `<div class="text-left"><pre>${currentState.finalReport}</pre></div>` : ''}
              <button class="btn btn-primary" onclick="location.reload()">
                Start New Request
              </button>
            </div>
          </div>
        </div>
      `;
    });
  }

  renderError() {
    const currentState = this.stateManager.getState();

    this.elements.content.innerHTML = `
      <div class="card">
        <div class="card-header">
          <h2 class="card-title text-error">Error</h2>
          <p class="card-description">Something went wrong during execution</p>
        </div>
        
        <div class="py-6 text-center">
          <div class="mb-4">
            <p class="text-error mb-2">${currentState.error || 'An unexpected error occurred'}</p>
            ${!currentState.apiConnected ? '<p class="text-warning">⚠️ API connection lost</p>' : ''}
          </div>
          
          <div class="space-x-2">
            <button class="btn btn-primary" id="reset-to-idle-btn">
              Try Again
            </button>
            <button class="btn btn-secondary" onclick="location.reload()">
              Restart Application
            </button>
          </div>
          
          ${currentState.preferences.debugMode ? `
            <details class="mt-4 text-left">
              <summary class="cursor-pointer text-sm text-secondary">Debug Information</summary>
              <pre class="text-xs mt-2 p-2 bg-gray-100 rounded">${JSON.stringify(currentState.lastError, null, 2)}</pre>
            </details>
          ` : ''}
        </div>
      </div>
    `;

    // Add event listener for reset button
    const resetBtn = this.elements.content.querySelector('#reset-to-idle-btn');
    if (resetBtn) {
      resetBtn.addEventListener('click', () => this.resetToIdle());
    }
  }

  resetToIdle() {
    this.stateManager.setState({
      status: 'idle',
      error: null,
      lastError: null,
      threadId: null,
      plan: null,
      progress: 0,
      isLoading: false
    }, 'user.reset');
  }

  /**
   * Cleanup specified components to prevent memory leaks
   */
  cleanupComponents(componentNames) {
    componentNames.forEach(componentName => {
      if (this[componentName]) {
        if (typeof this[componentName].destroy === 'function') {
          this[componentName].destroy();
        } else if (typeof this[componentName].reset === 'function') {
          this[componentName].reset();
        }
        this[componentName] = null;
      }
    });
  }

  handleError(error) {
    console.error('Application error:', error);
    this.stateManager.setState({
      status: 'error',
      error: error.message || 'An unexpected error occurred',
      lastError: {
        message: error.message,
        stack: error.stack,
        timestamp: new Date().toISOString()
      }
    }, 'app.handleError');
  }

  handleApiError(errorData) {
    console.error('API error received:', errorData);

    // Don't override current error state if already in error
    const currentState = this.stateManager.getState();
    if (currentState.status === 'error') {
      return;
    }

    this.stateManager.setState({
      status: 'error',
      error: errorData.error || 'API communication failed',
      lastError: {
        message: errorData.error,
        context: errorData.context,
        details: errorData.details,
        timestamp: errorData.timestamp
      },
      apiConnected: false
    }, 'app.handleApiError');
  }



  /**
   * Render approval phase where user can approve or reject the plan
   */
  renderApproval() {
    const currentState = this.stateManager.getState();
    console.log('[ClarityApp] Rendering approval phase with plan:', currentState.plan?.length, 'tasks');

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
      this.planVerification = new PlanVerification(planVerificationContainer, this.eventBus, this.apiService);
    }

    // Display the current plan
    if (currentState.plan && currentState.threadId) {
      console.log('[ClarityApp] Emitting planReceived event with', currentState.plan.length, 'tasks');
      // Trigger plan display through event bus
      this.eventBus.emit('planReceived', {
        plan: currentState.plan,
        threadId: currentState.threadId
      });
    } else {
      console.warn('[ClarityApp] Missing plan or threadId for approval rendering:', {
        hasPlan: !!currentState.plan,
        hasThreadId: !!currentState.threadId
      });
    }
  }


}

// Initialize application when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  window.clarityApp = new ClarityApp();
});

// Export for potential testing
export { ClarityApp };
