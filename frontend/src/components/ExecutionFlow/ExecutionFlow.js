/**
 * ExecutionFlow Component
 * 
 * Provides real-time visualization of workflow progress including:
 * - Task dependency visualization using CSS Grid and Flexbox
 * - Real-time status updates through efficient polling
 * - Responsive design for different screen sizes
 * - Progress tracking and completion status
 */

import { DOMUtils } from '../../utils/dom.js';

export class ExecutionFlow {
    constructor(stateManager, apiService) {
        this.stateManager = stateManager;
        this.apiService = apiService;
        this.element = null;

        // Component state
        this.currentStatus = null;
        this.tasks = [];
        this.progress = 0;

        // DOM element cache
        this.elements = {};

        // Bind methods
        this.handleStatusUpdate = this.handleStatusUpdate.bind(this);
        this.handleRetry = this.handleRetry.bind(this);
        this.handleCancel = this.handleCancel.bind(this);
        this.handleStateChange = this.handleStateChange.bind(this);

        // Subscribe to state changes
        this.unsubscribe = this.stateManager.subscribe(this.handleStateChange);
    }

    /**
     * Render the ExecutionFlow component
     */
    render() {
        if (this.element) {
            this.update();
            return this.element;
        }

        this.element = DOMUtils.createElement('div', 'execution-flow');
        this.element.innerHTML = this.getTemplate();

        // Cache DOM elements
        this.cacheElements();

        // Setup event listeners
        this.setupEventListeners();

        // Initialize with current state
        console.log('[ExecutionFlow] Initializing with current state');
        this.updateFromState();

        // Force an immediate update to ensure visibility
        setTimeout(() => {
            console.log('[ExecutionFlow] Performing delayed state update');
            this.updateFromState();
        }, 100);

        return this.element;
    }

    /**
     * Get the HTML template for the component
     */
    getTemplate() {
        return `
            <div class="execution-flow-container">
                <div class="execution-flow-header">
                    <div class="execution-flow-title">
                        <h2 class="card-title">Workflow Execution</h2>
                        <p class="card-description">Multi-agent task orchestration in progress</p>
                    </div>
                    
                    <div class="execution-flow-controls">
                        <button class="btn btn-secondary execution-flow-retry" style="display: none;">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
                                <path d="M21 3v5h-5"/>
                                <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
                                <path d="M3 21v-5h5"/>
                            </svg>
                            Retry
                        </button>
                        
                        <button class="btn btn-secondary execution-flow-cancel">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M18 6L6 18"/>
                                <path d="M6 6l12 12"/>
                            </svg>
                            Cancel
                        </button>
                    </div>
                </div>

                <div class="execution-flow-progress">
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: 0%"></div>
                    </div>
                    <div class="progress-text">
                        <span class="progress-percentage">0%</span>
                        <span class="progress-status">Initializing...</span>
                    </div>
                </div>

                <div class="execution-flow-content">
                    <div class="execution-flow-details">
                        <div class="current-task-info">
                            <h3>Current Task</h3>
                            <p class="current-task-description">Waiting for task assignment...</p>
                        </div>
                        
                        <div class="agent-status">
                            <h3>Agent Status</h3>
                            <div class="agent-list">
                                <!-- Agent status will be rendered here -->
                            </div>
                        </div>
                    </div>
                </div>

                <div class="execution-flow-loading" style="display: none;">
                    <div class="loading-spinner"></div>
                    <p>Loading workflow status...</p>
                </div>

                <div class="execution-flow-error" style="display: none;">
                    <div class="error-icon">⚠️</div>
                    <h3>Execution Error</h3>
                    <p class="error-message">An error occurred during workflow execution.</p>
                    <button class="btn btn-primary error-retry">Try Again</button>
                </div>
            </div>
        `;
    }

    /**
     * Cache DOM elements for efficient updates
     */
    cacheElements() {
        this.elements = {
            container: this.element.querySelector('.execution-flow-container'),
            header: this.element.querySelector('.execution-flow-header'),
            progressBar: this.element.querySelector('.progress-fill'),
            progressText: this.element.querySelector('.progress-percentage'),
            progressStatus: this.element.querySelector('.progress-status'),
            currentTaskInfo: this.element.querySelector('.current-task-info'),
            currentTaskDescription: this.element.querySelector('.current-task-description'),
            agentList: this.element.querySelector('.agent-list'),
            loadingState: this.element.querySelector('.execution-flow-loading'),
            errorState: this.element.querySelector('.execution-flow-error'),
            errorMessage: this.element.querySelector('.error-message'),
            retryButton: this.element.querySelector('.execution-flow-retry'),
            cancelButton: this.element.querySelector('.execution-flow-cancel'),
            errorRetryButton: this.element.querySelector('.error-retry')
        };
    }

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // Control buttons
        this.elements.retryButton?.addEventListener('click', this.handleRetry);
        this.elements.cancelButton?.addEventListener('click', this.handleCancel);
        this.elements.errorRetryButton?.addEventListener('click', this.handleRetry);

        // Responsive handling
        window.addEventListener('resize', () => this.handleResize());
    }

    /**
     * Handle state changes from state manager
     */
    handleStateChange(stateChangeData) {
        const { newState, previousState } = stateChangeData;

        console.log('[ExecutionFlow] State change received:', {
            status: newState.status,
            previousStatus: previousState?.status,
            plan: newState.plan?.length,
            progress: newState.progress,
            taskResults: Object.keys(newState.taskResults || {}).length
        });

        // Update if we're in executing status OR if we just transitioned to executing
        if (newState.status === 'executing' ||
            (previousState?.status !== 'executing' && newState.status === 'executing')) {
            console.log('[ExecutionFlow] Updating UI for executing status');
            this.updateFromState();
        }

        // Also update if progress changed during execution
        if (newState.status === 'executing' &&
            previousState?.progress !== newState.progress) {
            console.log('[ExecutionFlow] Progress updated during execution:', {
                from: previousState?.progress,
                to: newState.progress
            });
            this.updateFromState();
        }
    }

    /**
     * Update component from current state
     */
    updateFromState() {
        const currentState = this.stateManager.getState();

        if (currentState.status !== 'executing') {
            console.log('[ExecutionFlow] Not updating - status is not executing:', currentState.status);
            return;
        }

        console.log('[ExecutionFlow] Updating from state:', {
            tasks: currentState.plan?.length,
            progress: currentState.progress,
            taskResults: Object.keys(currentState.taskResults || {}).length,
            currentTaskId: currentState.currentTaskId,
            fullState: currentState
        });

        // Update component state from global state
        this.tasks = currentState.plan || [];
        this.progress = currentState.progress || 0;
        this.currentStatus = {
            status: currentState.status,
            plan: currentState.plan,
            progress: currentState.progress,
            task_results: currentState.taskResults
        };

        // Update UI immediately
        this.hideLoading();
        this.hideError();
        this.updateProgress();
        this.updateCurrentTask();
        this.updateAgentStatus();

        console.log('[ExecutionFlow] UI updated with progress:', this.progress);
    }

    /**
     * Handle status updates from polling
     */
    handleStatusUpdate(statusData) {
        if (!statusData.success) {
            this.showError('Failed to fetch workflow status');
            return;
        }

        this.currentStatus = statusData;
        this.tasks = statusData.plan || [];
        this.progress = statusData.progress || 0;

        // Update UI
        this.hideLoading();
        this.hideError();
        this.updateProgress();
        this.updateCurrentTask();
        this.updateAgentStatus();

        // Handle completion
        if (['completed', 'failed', 'cancelled'].includes(statusData.status)) {
            this.stopPolling();
            this.handleWorkflowComplete(statusData);
        }
    }

    /**
     * Update progress bar and text
     */
    updateProgress() {
        const percentage = Math.round(this.progress * 100);

        this.elements.progressBar.style.width = `${percentage}%`;
        this.elements.progressText.textContent = `${percentage}%`;

        // Update status text with more engaging messages
        let statusText = this.getProgressStatusText(percentage);

        this.elements.progressStatus.textContent = statusText;
    }

    /**
     * Get engaging progress status text based on percentage
     */
    getProgressStatusText(percentage) {
        if (percentage === 0) {
            return 'Initializing task execution...';
        } else if (percentage < 20) {
            return 'Setting up execution environment...';
        } else if (percentage < 40) {
            return 'Processing first set of tasks...';
        } else if (percentage < 60) {
            return 'Making good progress on tasks...';
        } else if (percentage < 80) {
            return 'Completing remaining tasks...';
        } else if (percentage < 95) {
            return 'Finalizing results...';
        } else if (percentage < 100) {
            return 'Almost done, preparing final report...';
        } else {
            return 'Completed successfully!';
        }
    }









    /**
     * Update current task information
     */
    updateCurrentTask() {
        const currentState = this.stateManager.getState();
        const progress = currentState.simulatedProgress || 0;

        // If we have real task data, use it
        if (this.currentStatus && this.tasks) {
            const currentTask = this.tasks.find(task => task.status === 'in_progress');
            if (currentTask) {
                this.elements.currentTaskDescription.innerHTML = `
                    <strong>Task #${currentTask.id}:</strong> ${currentTask.description}
                    <br><small>Type: ${currentTask.type}</small>
                `;
                return;
            }
        }

        // Otherwise, show simulated current task based on progress
        let currentTaskText = 'Preparing to start execution...';

        if (progress > 0.80) {
            currentTaskText = '<strong>Finalizing:</strong> Compiling final report and recommendations<br><small>Agent: Execution</small>';
        } else if (progress > 0.60) {
            currentTaskText = '<strong>Processing:</strong> Analyzing data and creating insights<br><small>Agent: Execution</small>';
        } else if (progress > 0.40) {
            currentTaskText = '<strong>Synthesizing:</strong> Organizing and structuring information<br><small>Agent: Execution</small>';
        } else if (progress > 0.20) {
            currentTaskText = '<strong>Researching:</strong> Gathering comprehensive information<br><small>Agent: Research</small>';
        } else if (progress > 0.05) {
            currentTaskText = '<strong>Initializing:</strong> Setting up research parameters<br><small>Agent: Research</small>';
        } else if (progress > 0) {
            currentTaskText = '<strong>Starting:</strong> Preparing execution environment<br><small>System</small>';
        }

        this.elements.currentTaskDescription.innerHTML = currentTaskText;
    }

    /**
     * Update agent status display
     */
    updateAgentStatus() {
        const currentState = this.stateManager.getState();
        const progress = currentState.simulatedProgress || 0;

        // Simplified 2-agent system for clarity
        const agents = [
            { name: 'Research Agent', status: 'idle', type: 'research' },
            { name: 'Execution Agent', status: 'idle', type: 'execution' }
        ];

        // Determine active agent based on progress
        if (progress > 0.95) {
            // All tasks completed
            agents[0].status = 'completed'; // Research Agent
            agents[1].status = 'completed'; // Execution Agent
        } else if (progress > 0.50) {
            // Execution phase (analysis, summary, recommendations)
            agents[0].status = 'completed'; // Research Agent (research tasks done)
            agents[1].status = 'active'; // Execution Agent (processing and creating outputs)
        } else if (progress > 0.05) {
            // Research phase (gathering information)
            agents[0].status = 'active'; // Research Agent
            agents[1].status = 'idle'; // Execution Agent
        }

        // If we have real task data, use it to override simulation
        if (this.currentStatus && this.tasks) {
            const currentTask = this.tasks.find(task => task.status === 'in_progress');
            if (currentTask) {
                // Reset all to idle first
                agents.forEach(agent => agent.status = 'idle');

                // Set active agent based on task type
                const activeAgent = agents.find(agent => agent.type === currentTask.type);
                if (activeAgent) {
                    activeAgent.status = 'active';
                }

                // Mark completed agents based on completed tasks
                const completedTaskTypes = this.tasks
                    .filter(task => task.status === 'completed')
                    .map(task => task.type);

                agents.forEach(agent => {
                    if (completedTaskTypes.includes(agent.type) && agent.status !== 'active') {
                        agent.status = 'completed';
                    }
                });
            }
        }

        this.elements.agentList.innerHTML = agents.map(agent => `
            <div class="agent-status-item ${agent.status}">
                <div class="agent-indicator"></div>
                <span class="agent-name">${agent.name}</span>
                <span class="agent-status-text">${agent.status}</span>
            </div>
        `).join('');
    }

    /**
     * Handle workflow completion
     */
    handleWorkflowComplete(statusData) {
        if (statusData.status === 'completed') {
            this.elements.progressBar.style.width = '100%';
            this.elements.progressText.textContent = '100%';
            this.elements.progressStatus.textContent = 'Completed successfully!';

            // Show retry button for new requests
            DOMUtils.show(this.elements.retryButton);
        } else if (statusData.status === 'failed') {
            this.showError(statusData.error || 'Workflow execution failed');
        }
    }

    /**
     * Show loading state
     */
    showLoading() {
        DOMUtils.show(this.elements.loadingState);
        DOMUtils.hide(this.elements.errorState);
    }

    /**
     * Hide loading state
     */
    hideLoading() {
        DOMUtils.hide(this.elements.loadingState);
    }

    /**
     * Show error state
     */
    showError(message) {
        this.elements.errorMessage.textContent = message;
        DOMUtils.show(this.elements.errorState);
        DOMUtils.hide(this.elements.loadingState);
        DOMUtils.show(this.elements.retryButton);
    }

    /**
     * Hide error state
     */
    hideError() {
        DOMUtils.hide(this.elements.errorState);
    }

    /**
     * Handle retry action
     */
    handleRetry() {
        const currentState = this.stateManager.getState();
        if (currentState.threadId) {
            // Reset to planning state to restart workflow
            this.stateManager.setState({
                status: 'planning',
                error: null,
                lastError: null
            }, 'executionFlow.retry');
        }
    }

    /**
     * Handle cancel action
     */
    async handleCancel() {
        const currentState = this.stateManager.getState();
        if (!currentState.threadId) return;

        try {
            // Emit cancel event for API service to handle
            this.apiService.eventBus.emit('cancelWorkflow', {
                threadId: currentState.threadId
            });

            this.elements.progressStatus.textContent = 'Cancelling workflow...';
        } catch (error) {
            console.error('Failed to cancel workflow:', error);
            this.showError('Failed to cancel workflow');
        }
    }

    /**
     * Handle window resize for responsive design
     */
    handleResize() {
        // Adjust task graph layout for different screen sizes
        const container = this.elements.taskGraph;
        if (!container) return;

        const width = container.offsetWidth;

        if (width < 768) {
            container.classList.add('mobile-layout');
        } else {
            container.classList.remove('mobile-layout');
        }
    }

    /**
     * Utility: Truncate text
     */
    truncateText(text, maxLength) {
        if (!text || text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    }

    /**
     * Update component with new state
     */
    update() {
        this.updateFromState();
    }

    /**
     * Cleanup component
     */
    destroy() {
        // Unsubscribe from state changes
        if (this.unsubscribe) {
            this.unsubscribe();
        }

        // Remove event listeners
        window.removeEventListener('resize', this.handleResize);

        if (this.element) {
            this.element.remove();
            this.element = null;
        }
    }
}