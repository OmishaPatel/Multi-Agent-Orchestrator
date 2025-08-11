import { DOMUtils } from '../../utils/dom.js';

export class PlanVerification {
    constructor(container, eventBus, apiService) {
        this.container = container;
        this.eventBus = eventBus;
        this.apiService = apiService;
        this.currentPlan = null;
        this.threadId = null;
        this.feedbackText = '';
        this.isSubmitting = false;

        this.init();
    }

    init() {
        this.container.className = 'plan-verification';
        this.render();
        this.bindEvents();
    }

    render() {
        this.container.innerHTML = `
            <div class="plan-verification__header">
                <h2 class="plan-verification__title">
                    <span class="plan-verification__icon">🔍</span>
                    Review Execution Plan
                </h2>
                <p class="plan-verification__subtitle">
                    Please review the AI-generated plan before execution begins
                </p>
            </div>
            
            <div class="plan-verification__content">
                <div class="plan-verification__plan-display" id="planDisplay">
                    <!-- Plan will be rendered here -->
                </div>
                
                <div class="plan-verification__feedback-section">
                    <label for="feedbackInput" class="plan-verification__feedback-label">
                        Feedback or Modifications (Optional)
                    </label>
                    <textarea 
                        id="feedbackInput"
                        class="plan-verification__feedback-input"
                        placeholder="Provide feedback to improve the plan, suggest changes, or add requirements..."
                        rows="4"
                    ></textarea>
                    <div class="plan-verification__feedback-counter">
                        <span id="feedbackCounter">0</span> / 1000 characters
                    </div>
                </div>
                
                <div class="plan-verification__actions">
                    <button 
                        type="button" 
                        class="plan-verification__button plan-verification__button--reject"
                        id="rejectButton"
                        disabled
                    >
                        <span class="plan-verification__button-icon">❌</span>
                        Request Changes
                    </button>
                    
                    <button 
                        type="button" 
                        class="plan-verification__button plan-verification__button--approve"
                        id="approveButton"
                        disabled
                    >
                        <span class="plan-verification__button-icon">✅</span>
                        Approve & Execute
                    </button>
                </div>
                
                <div class="plan-verification__status" id="statusMessage">
                    <!-- Status messages will appear here -->
                </div>
            </div>
        `;
    }

    bindEvents() {
        const feedbackInput = this.container.querySelector('#feedbackInput');
        const feedbackCounter = this.container.querySelector('#feedbackCounter');
        const approveButton = this.container.querySelector('#approveButton');
        const rejectButton = this.container.querySelector('#rejectButton');

        // Feedback input handling
        feedbackInput.addEventListener('input', (e) => {
            this.feedbackText = e.target.value;
            const length = this.feedbackText.length;
            feedbackCounter.textContent = length;

            // Update counter color based on length
            if (length > 1000) {
                feedbackCounter.classList.add('plan-verification__feedback-counter--error');
                e.target.classList.add('plan-verification__feedback-input--error');
            } else {
                feedbackCounter.classList.remove('plan-verification__feedback-counter--error');
                e.target.classList.remove('plan-verification__feedback-input--error');
            }

            this.validateForm();
        });

        // Button event handlers
        approveButton.addEventListener('click', () => this.handleApproval(true));
        rejectButton.addEventListener('click', () => this.handleApproval(false));

        // Listen for plan received events through event bus
        this.eventBus.on('planReceived', (data) => {
            this.displayPlan(data.plan, data.threadId);
        });
    }

    displayPlan(plan, threadId) {
        this.currentPlan = plan;
        this.threadId = threadId;

        const planDisplay = this.container.querySelector('#planDisplay');
        DOMUtils.clearElement(planDisplay);

        if (!plan || !Array.isArray(plan) || plan.length === 0) {
            planDisplay.innerHTML = `
                <div class="plan-verification__empty">
                    <p>No plan available to review.</p>
                </div>
            `;
            return;
        }

        // Create plan overview
        const overview = DOMUtils.createElement('div', 'plan-verification__overview');
        overview.innerHTML = `
            <h3 class="plan-verification__overview-title">
                Plan Overview
            </h3>
            <div class="plan-verification__overview-stats">
                <span class="plan-verification__stat">
                    <strong>${plan.length}</strong> tasks
                </span>
                <span class="plan-verification__stat">
                    <strong>${this.getUniqueTaskTypes(plan).length}</strong> agent types
                </span>
                <span class="plan-verification__stat">
                    <strong>${this.calculateEstimatedTime(plan)}</strong> estimated time
                </span>
            </div>
        `;
        planDisplay.appendChild(overview);

        // Create task list
        const taskList = DOMUtils.createElement('div', 'plan-verification__task-list');

        plan.forEach((task, index) => {
            const taskElement = this.createTaskElement(task, index);
            taskList.appendChild(taskElement);
        });

        planDisplay.appendChild(taskList);

        // Enable form validation
        this.validateForm();
    }

    createTaskElement(task, index) {
        const taskElement = DOMUtils.createElement('div', 'plan-verification__task');

        // Add task type class for styling
        taskElement.classList.add(`plan-verification__task--${task.type}`);

        // Check if task has dependencies
        const hasDependencies = task.dependencies && task.dependencies.length > 0;

        taskElement.innerHTML = `
            <div class="plan-verification__task-header">
                <div class="plan-verification__task-number">${index + 1}</div>
                <div class="plan-verification__task-type">
                    ${this.getTaskTypeIcon(task.type)} ${this.formatTaskType(task.type)}
                </div>
                ${hasDependencies ? `
                    <div class="plan-verification__task-dependencies">
                        Depends on: ${task.dependencies.map(dep => `#${dep + 1}`).join(', ')}
                    </div>
                ` : ''}
            </div>
            
            <div class="plan-verification__task-content">
                <h4 class="plan-verification__task-title">
                    ${this.escapeHtml(task.description)}
                </h4>
                
                ${task.details ? `
                    <div class="plan-verification__task-details">
                        <p>${this.escapeHtml(task.details)}</p>
                    </div>
                ` : ''}
                
                <div class="plan-verification__task-meta">
                    <span class="plan-verification__task-status">
                        Status: ${task.status || 'pending'}
                    </span>
                    <span class="plan-verification__task-estimated-time">
                        ~${this.getTaskEstimatedTime(task.type)} min
                    </span>
                </div>
            </div>
        `;

        return taskElement;
    }

    getTaskTypeIcon(type) {
        const icons = {
            'research': '🔍',
            'code': '💻',
            'analysis': '📊',
            'summary': '📝',
            'calculation': '🧮'
        };
        return icons[type] || '📋';
    }

    formatTaskType(type) {
        return type.charAt(0).toUpperCase() + type.slice(1);
    }

    getTaskEstimatedTime(type) {
        const times = {
            'research': '3-5',
            'code': '5-10',
            'analysis': '2-4',
            'summary': '1-3',
            'calculation': '2-5'
        };
        return times[type] || '2-5';
    }

    getUniqueTaskTypes(plan) {
        return [...new Set(plan.map(task => task.type))];
    }

    calculateEstimatedTime(plan) {
        const totalMinutes = plan.reduce((total, task) => {
            const timeRange = this.getTaskEstimatedTime(task.type);
            const avgTime = timeRange.includes('-')
                ? (parseInt(timeRange.split('-')[0]) + parseInt(timeRange.split('-')[1])) / 2
                : parseInt(timeRange);
            return total + avgTime;
        }, 0);

        if (totalMinutes < 60) {
            return `${Math.round(totalMinutes)} min`;
        } else {
            const hours = Math.floor(totalMinutes / 60);
            const minutes = Math.round(totalMinutes % 60);
            return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
        }
    }

    validateForm() {
        const approveButton = this.container.querySelector('#approveButton');
        const rejectButton = this.container.querySelector('#rejectButton');

        const hasValidPlan = this.currentPlan && this.threadId;
        const feedbackValid = this.feedbackText.length <= 1000;
        const notSubmitting = !this.isSubmitting;

        const canProceed = hasValidPlan && feedbackValid && notSubmitting;

        approveButton.disabled = !canProceed;
        rejectButton.disabled = !canProceed;
    }

    async handleApproval(approved) {
        if (this.isSubmitting) return;

        this.isSubmitting = true;
        this.updateSubmissionState(true);

        try {
            this.showStatusMessage(
                approved ? 'Submitting approval...' : 'Submitting feedback...',
                'info'
            );

            // Emit approval event through event bus for API service to handle
            this.eventBus.emit('planApproval', {
                threadId: this.threadId,
                approved: approved,
                feedback: this.feedbackText.trim() || null
            });

            this.showStatusMessage(
                approved ? 'Plan approved! Execution starting...' : 'Feedback submitted. Generating new plan...',
                'success'
            );

            // Clear form if approved
            if (approved) {
                this.clearForm();
            }

        } catch (error) {
            console.error('Approval submission error:', error);
            this.showStatusMessage(
                `Error: ${error.message || 'Failed to submit approval'}. Please try again.`,
                'error'
            );
        } finally {
            this.isSubmitting = false;
            this.updateSubmissionState(false);
        }
    }

    updateSubmissionState(submitting) {
        const approveButton = this.container.querySelector('#approveButton');
        const rejectButton = this.container.querySelector('#rejectButton');
        const feedbackInput = this.container.querySelector('#feedbackInput');

        if (submitting) {
            approveButton.classList.add('plan-verification__button--loading');
            rejectButton.classList.add('plan-verification__button--loading');
            approveButton.textContent = 'Submitting...';
            rejectButton.textContent = 'Submitting...';
            feedbackInput.disabled = true;
        } else {
            approveButton.classList.remove('plan-verification__button--loading');
            rejectButton.classList.remove('plan-verification__button--loading');
            approveButton.innerHTML = '<span class="plan-verification__button-icon">✅</span> Approve & Execute';
            rejectButton.innerHTML = '<span class="plan-verification__button-icon">❌</span> Request Changes';
            feedbackInput.disabled = false;
        }

        this.validateForm();
    }

    showStatusMessage(message, type = 'info') {
        const statusElement = this.container.querySelector('#statusMessage');
        statusElement.className = `plan-verification__status plan-verification__status--${type}`;
        statusElement.textContent = message;

        // Auto-hide success messages
        if (type === 'success') {
            setTimeout(() => {
                statusElement.textContent = '';
                statusElement.className = 'plan-verification__status';
            }, 3000);
        }
    }

    clearForm() {
        const feedbackInput = this.container.querySelector('#feedbackInput');
        const feedbackCounter = this.container.querySelector('#feedbackCounter');

        feedbackInput.value = '';
        this.feedbackText = '';
        feedbackCounter.textContent = '0';
        feedbackCounter.classList.remove('plan-verification__feedback-counter--error');
        feedbackInput.classList.remove('plan-verification__feedback-input--error');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Public methods for external control
    show() {
        this.container.style.display = 'block';
    }

    hide() {
        this.container.style.display = 'none';
    }

    reset() {
        this.currentPlan = null;
        this.threadId = null;
        this.clearForm();
        this.showStatusMessage('', 'info');

        const planDisplay = this.container.querySelector('#planDisplay');
        DOMUtils.clearElement(planDisplay);
    }

    destroy() {
        this.reset();
        // Remove any event listeners if needed
        if (this.container && this.container.parentNode) {
            this.container.parentNode.removeChild(this.container);
        }
    }
}