export class TaskCard {
    constructor(container, task, options = {}) {
        this.container = container;
        this.task = task;
        this.options = {
            showProgress: true,
            allowRetry: true,
            showDependencies: false,
            ...options
        };

        this.element = null;
        this.progressBar = null;
        this.statusIndicator = null;
        this.retryButton = null;

        this.init();
    }

    init() {
        this.createElement();
        this.bindEvents();
        this.render();
    }

    createElement() {
        this.element = document.createElement('div');
        this.element.className = 'task-card';
        this.element.setAttribute('data-task-id', this.task.id);
        this.element.setAttribute('data-task-status', this.task.status);

        this.element.innerHTML = `
            <div class="task-card__header">
                <div class="task-card__status-indicator">
                    <span class="status-icon" aria-hidden="true"></span>
                    <span class="status-text">${this.getStatusText()}</span>
                </div>
                <div class="task-card__id">Task ${this.task.id}</div>
            </div>
            
            <div class="task-card__content">
                <h3 class="task-card__title">${this.task.description}</h3>
                
                ${this.task.type ? `
                    <div class="task-card__type">
                        <span class="type-badge type-badge--${this.task.type}">
                            ${this.task.type.charAt(0).toUpperCase() + this.task.type.slice(1)}
                        </span>
                    </div>
                ` : ''}
                
                ${this.options.showProgress ? `
                    <div class="task-card__progress">
                        <div class="progress-bar">
                            <div class="progress-bar__fill" style="width: ${this.getProgressPercentage()}%"></div>
                        </div>
                        <span class="progress-text">${this.getProgressPercentage()}%</span>
                    </div>
                ` : ''}
                
                ${this.task.dependencies && this.task.dependencies.length > 0 && this.options.showDependencies ? `
                    <div class="task-card__dependencies">
                        <span class="dependencies-label">Depends on:</span>
                        <div class="dependencies-list">
                            ${this.task.dependencies.map(dep =>
            `<span class="dependency-tag">Task ${dep}</span>`
        ).join('')}
                        </div>
                    </div>
                ` : ''}
                
                ${this.task.result ? `
                    <div class="task-card__result">
                        <details class="result-details">
                            <summary>View Result</summary>
                            <div class="result-content">
                                ${this.formatResult(this.task.result)}
                            </div>
                        </details>
                    </div>
                ` : ''}
                
                ${this.task.error ? `
                    <div class="task-card__error">
                        <div class="error-message">
                            <span class="error-icon" aria-hidden="true">⚠️</span>
                            <span class="error-text">${this.task.error}</span>
                        </div>
                        ${this.options.allowRetry ? `
                            <button class="retry-button" type="button">
                                <span class="retry-icon" aria-hidden="true">🔄</span>
                                Retry Task
                            </button>
                        ` : ''}
                    </div>
                ` : ''}
            </div>
            
            <div class="task-card__footer">
                <div class="task-card__timestamp">
                    ${this.task.updated_at ? `Updated: ${this.formatTimestamp(this.task.updated_at)}` : ''}
                </div>
            </div>
        `;

        this.container.appendChild(this.element);

        // Cache important elements
        this.progressBar = this.element.querySelector('.progress-bar__fill');
        this.statusIndicator = this.element.querySelector('.task-card__status-indicator');
        this.retryButton = this.element.querySelector('.retry-button');
    }

    bindEvents() {
        if (this.retryButton) {
            this.retryButton.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleRetry();
            });
        }

        // Handle result details toggle
        const details = this.element.querySelector('.result-details');
        if (details) {
            details.addEventListener('toggle', (e) => {
                if (e.target.open) {
                    this.element.classList.add('task-card--expanded');
                } else {
                    this.element.classList.remove('task-card--expanded');
                }
            });
        }
    }

    getStatusText() {
        const statusMap = {
            'pending': 'Pending',
            'in_progress': 'In Progress',
            'completed': 'Completed',
            'failed': 'Failed',
            'cancelled': 'Cancelled'
        };
        return statusMap[this.task.status] || 'Unknown';
    }

    getProgressPercentage() {
        switch (this.task.status) {
            case 'completed': return 100;
            case 'in_progress': return this.task.progress || 50;
            case 'failed': return this.task.progress || 0;
            case 'cancelled': return this.task.progress || 0;
            default: return 0;
        }
    }

    formatResult(result) {
        if (typeof result === 'string') {
            // Simple text formatting
            return `<pre class="result-text">${this.escapeHtml(result)}</pre>`;
        } else if (typeof result === 'object') {
            // JSON formatting
            return `<pre class="result-json">${JSON.stringify(result, null, 2)}</pre>`;
        }
        return result;
    }

    formatTimestamp(timestamp) {
        try {
            const date = new Date(timestamp);
            return date.toLocaleString();
        } catch (e) {
            return timestamp;
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    handleRetry() {
        if (this.options.onRetry) {
            this.retryButton.disabled = true;
            this.retryButton.textContent = 'Retrying...';

            this.options.onRetry(this.task.id)
                .then(() => {
                    // Success handled by update method
                })
                .catch((error) => {
                    console.error('Retry failed:', error);
                    this.retryButton.disabled = false;
                    this.retryButton.innerHTML = `
                        <span class="retry-icon" aria-hidden="true">🔄</span>
                        Retry Task
                    `;
                });
        }
    }

    update(newTask) {
        const oldStatus = this.task.status;
        this.task = { ...this.task, ...newTask };

        // Update status indicator
        this.element.setAttribute('data-task-status', this.task.status);
        const statusText = this.element.querySelector('.status-text');
        if (statusText) {
            statusText.textContent = this.getStatusText();
        }

        // Update progress bar
        if (this.progressBar) {
            const percentage = this.getProgressPercentage();
            this.progressBar.style.width = `${percentage}%`;

            const progressText = this.element.querySelector('.progress-text');
            if (progressText) {
                progressText.textContent = `${percentage}%`;
            }
        }

        // Add animation for status changes
        if (oldStatus !== this.task.status) {
            this.element.classList.add('task-card--updating');
            setTimeout(() => {
                this.element.classList.remove('task-card--updating');
            }, 300);
        }

        // Update result if available
        if (this.task.result && !this.element.querySelector('.task-card__result')) {
            this.render(); // Re-render if result was added
        }

        // Update error state
        if (this.task.error && !this.element.querySelector('.task-card__error')) {
            this.render(); // Re-render if error was added
        }

        // Update timestamp
        const timestamp = this.element.querySelector('.task-card__timestamp');
        if (timestamp && this.task.updated_at) {
            timestamp.textContent = `Updated: ${this.formatTimestamp(this.task.updated_at)}`;
        }
    }

    render() {
        // Re-render is handled by createElement for now
        // In a more complex implementation, we'd update individual parts
    }

    destroy() {
        if (this.element && this.element.parentNode) {
            this.element.parentNode.removeChild(this.element);
        }
    }
}
