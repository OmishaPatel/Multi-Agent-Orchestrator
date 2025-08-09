/**
 * ExecutionFlow Component
 * 
 * Provides real-time visualization of workflow progress including:
 * - Task dependency visualization using CSS Grid and Flexbox
 * - Real-time status updates through efficient polling
 * - Responsive design for different screen sizes
 * - Progress tracking and completion status
 */

import { StatusPoller } from '../../utils/api.js';
import { DOMUtils } from '../../utils/dom.js';

export class ExecutionFlow {
    constructor(state, apiClient) {
        this.state = state;
        this.api = apiClient;
        this.poller = null;
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

        // Start polling if we have a thread ID
        if (this.state.threadId) {
            this.startPolling();
        }

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
                    <div class="task-dependency-graph">
                        <!-- Task visualization will be rendered here -->
                    </div>
                    
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
            taskGraph: this.element.querySelector('.task-dependency-graph'),
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
     * Start polling for status updates
     */
    startPolling() {
        if (this.poller) {
            this.poller.stop();
        }

        this.poller = new StatusPoller(
            this.api,
            this.state.threadId,
            this.handleStatusUpdate,
            {
                interval: 2000,
                maxAttempts: 300,
                backoffMultiplier: 1.1,
                maxInterval: 10000
            }
        );

        this.poller.start();
        this.showLoading();
    }

    /**
     * Stop polling
     */
    stopPolling() {
        if (this.poller) {
            this.poller.stop();
            this.poller = null;
        }
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
        this.updateTaskGraph();
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

        // Update status text based on current state
        let statusText = 'In Progress...';
        if (this.currentStatus) {
            switch (this.currentStatus.status) {
                case 'planning':
                    statusText = 'Planning workflow...';
                    break;
                case 'awaiting_approval':
                    statusText = 'Awaiting plan approval...';
                    break;
                case 'executing':
                    statusText = 'Executing tasks...';
                    break;
                case 'completed':
                    statusText = 'Completed successfully!';
                    break;
                case 'failed':
                    statusText = 'Execution failed';
                    break;
                case 'cancelled':
                    statusText = 'Cancelled by user';
                    break;
                default:
                    statusText = 'Processing...';
            }
        }

        this.elements.progressStatus.textContent = statusText;
    }

    /**
     * Update task dependency graph visualization
     */
    updateTaskGraph() {
        if (!this.tasks || this.tasks.length === 0) {
            this.elements.taskGraph.innerHTML = `
                <div class="task-graph-empty">
                    <p>No tasks available yet...</p>
                </div>
            `;
            return;
        }

        // Create task dependency visualization
        const graphHTML = this.renderTaskDependencyGraph();
        this.elements.taskGraph.innerHTML = graphHTML;
    }

    /**
     * Render task dependency graph using CSS Grid
     */
    renderTaskDependencyGraph() {
        // Sort tasks by dependencies to create proper layout
        const sortedTasks = this.topologicalSort(this.tasks);
        const taskLevels = this.calculateTaskLevels(sortedTasks);

        let html = '<div class="task-graph">';

        // Render tasks by levels
        taskLevels.forEach((level, levelIndex) => {
            html += `<div class="task-level" data-level="${levelIndex}">`;

            level.forEach(task => {
                const statusClass = this.getTaskStatusClass(task.status);
                const isActive = task.status === 'in_progress';

                html += `
                    <div class="task-node ${statusClass} ${isActive ? 'active' : ''}" 
                         data-task-id="${task.id}"
                         title="${task.description}">
                        <div class="task-node-header">
                            <span class="task-id">#${task.id}</span>
                            <span class="task-type">${task.type}</span>
                        </div>
                        <div class="task-node-content">
                            <h4 class="task-title">${this.truncateText(task.description, 50)}</h4>
                            <div class="task-status">
                                ${this.getStatusIcon(task.status)}
                                <span>${this.formatStatus(task.status)}</span>
                            </div>
                        </div>
                        ${task.result ? `<div class="task-result-preview">${this.truncateText(task.result, 100)}</div>` : ''}
                    </div>
                `;
            });

            html += '</div>';
        });

        html += '</div>';

        // Add dependency lines if needed
        html += this.renderDependencyLines(sortedTasks);

        return html;
    }

    /**
     * Topological sort for task dependencies
     */
    topologicalSort(tasks) {
        const visited = new Set();
        const result = [];
        const taskMap = new Map(tasks.map(task => [task.id, task]));

        function visit(taskId) {
            if (visited.has(taskId)) return;
            visited.add(taskId);

            const task = taskMap.get(taskId);
            if (task && task.dependencies) {
                task.dependencies.forEach(depId => visit(depId));
            }

            if (task) result.push(task);
        }

        tasks.forEach(task => visit(task.id));
        return result;
    }

    /**
     * Calculate task levels for visualization
     */
    calculateTaskLevels(tasks) {
        const levels = [];
        const taskLevelMap = new Map();

        tasks.forEach(task => {
            let level = 0;
            if (task.dependencies && task.dependencies.length > 0) {
                level = Math.max(...task.dependencies.map(depId =>
                    (taskLevelMap.get(depId) || 0) + 1
                ));
            }

            taskLevelMap.set(task.id, level);

            if (!levels[level]) levels[level] = [];
            levels[level].push(task);
        });

        return levels;
    }

    /**
     * Get CSS class for task status
     */
    getTaskStatusClass(status) {
        const statusMap = {
            'pending': 'task-pending',
            'in_progress': 'task-in-progress',
            'completed': 'task-completed',
            'failed': 'task-failed',
            'cancelled': 'task-cancelled'
        };
        return statusMap[status] || 'task-unknown';
    }

    /**
     * Get status icon
     */
    getStatusIcon(status) {
        const icons = {
            'pending': '⏳',
            'in_progress': '🔄',
            'completed': '✅',
            'failed': '❌',
            'cancelled': '⏹️'
        };
        return icons[status] || '❓';
    }

    /**
     * Format status text
     */
    formatStatus(status) {
        return status.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    /**
     * Render dependency lines (simplified version)
     */
    renderDependencyLines(tasks) {
        // For now, return empty - complex SVG lines would require more sophisticated positioning
        return '<div class="dependency-lines"></div>';
    }

    /**
     * Update current task information
     */
    updateCurrentTask() {
        if (!this.currentStatus || !this.tasks) return;

        const currentTask = this.tasks.find(task => task.status === 'in_progress');

        if (currentTask) {
            this.elements.currentTaskDescription.innerHTML = `
                <strong>Task #${currentTask.id}:</strong> ${currentTask.description}
                <br><small>Type: ${currentTask.type}</small>
            `;
        } else {
            this.elements.currentTaskDescription.textContent = 'No active task';
        }
    }

    /**
     * Update agent status display
     */
    updateAgentStatus() {
        if (!this.currentStatus) return;

        const agents = [
            { name: 'Planning Agent', status: 'idle', type: 'planning' },
            { name: 'Research Agent', status: 'idle', type: 'research' },
            { name: 'Code Agent', status: 'idle', type: 'code' }
        ];

        // Determine active agent based on current task
        const currentTask = this.tasks.find(task => task.status === 'in_progress');
        if (currentTask) {
            const activeAgent = agents.find(agent => agent.type === currentTask.type);
            if (activeAgent) {
                activeAgent.status = 'active';
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
        if (this.state.threadId) {
            this.startPolling();
        }
    }

    /**
     * Handle cancel action
     */
    async handleCancel() {
        if (!this.state.threadId) return;

        try {
            const result = await this.api.cancelWorkflow(this.state.threadId);
            if (result.success) {
                this.stopPolling();
                this.elements.progressStatus.textContent = 'Cancelled by user';
            }
        } catch (error) {
            console.error('Failed to cancel workflow:', error);
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
        if (this.state.threadId && !this.poller) {
            this.startPolling();
        }
    }

    /**
     * Cleanup component
     */
    destroy() {
        this.stopPolling();

        // Remove event listeners
        window.removeEventListener('resize', this.handleResize);

        if (this.element) {
            this.element.remove();
            this.element = null;
        }
    }
}