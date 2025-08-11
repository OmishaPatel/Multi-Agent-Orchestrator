/**
 * InputForm Component
 * Handles user request submission with validation, error handling, and loading states
 */

import { DOMUtils } from '../../utils/dom.js';

export class InputForm {
    constructor(stateManager, apiService) {
        this.stateManager = stateManager;
        this.apiService = apiService;
        this.element = null;
        this.form = null;
        this.textarea = null;
        this.submitButton = null;
        this.errorContainer = null;
        this.charCounter = null;

        // Configuration
        this.config = {
            minLength: 10,
            maxLength: 2000,
            placeholder: 'Describe your complex task or project. For example:\n\n"Research the latest trends in renewable energy, analyze the market potential for solar panels in residential areas, and create a business plan with financial projections for a solar installation company."',
            submitText: 'Start Workflow',
            loadingText: 'Creating Plan...'
        };

        this.init();
    }

    init() {
        this.createElement();
        this.setupEventListeners();
        this.setupValidation();
    }

    createElement() {
        this.element = DOMUtils.createElement('div', 'input-form-container');

        this.element.innerHTML = `
      <div class="card">
        <div class="card-header">
          <h2 class="card-title">Submit Your Request</h2>
          <p class="card-description">
            Describe your complex task and let our AI agents create a structured execution plan
          </p>
        </div>
        
        <form class="input-form" id="request-form" novalidate>
          <div class="form-group">
            <label for="request-input" class="form-label">
              Task Description
              <span class="required-indicator">*</span>
            </label>
            <textarea
              id="request-input"
              name="request"
              class="form-textarea"
              placeholder="${this.config.placeholder}"
              rows="6"
              required
              minlength="${this.config.minLength}"
              maxlength="${this.config.maxLength}"
            ></textarea>
            <div class="form-meta">
              <div class="char-counter">
                <span id="char-count">0</span>/${this.config.maxLength}
              </div>
              <div class="form-hint">
                Minimum ${this.config.minLength} characters required. Be specific about your task or project.
              </div>
            </div>
            <div class="form-error" id="request-error" role="alert"></div>
          </div>
          
          <div class="form-group">
            <label class="form-checkbox-label">
              <input type="checkbox" id="terms-checkbox" class="form-checkbox" required>
              <span class="checkbox-text">
                I understand that this request will be processed by AI agents and may involve web searches and code execution
              </span>
            </label>
            <div class="form-error" id="terms-error" role="alert"></div>
          </div>
          
          <div class="form-actions">
            <button type="submit" class="btn btn-primary btn-large" id="submit-button">
              <span class="btn-text">${this.config.submitText}</span>
              <span class="btn-loading" style="display: none;">
                <span class="loading-spinner"></span>
                ${this.config.loadingText}
              </span>
            </button>
            
            <button type="button" class="btn btn-secondary" id="clear-button">
              Clear Form
            </button>
          </div>
        </form>
        
        <div class="form-tips">
          <h3 class="tips-title">💡 Tips for Better Requests</h3>
          <ul class="tips-list">
            <li><strong>Be specific:</strong> Instead of "help me with research," try "research renewable energy market trends in Europe"</li>
            <li><strong>Include context:</strong> Mention your goal, timeline, or specific requirements</li>
            <li><strong>Describe deliverables:</strong> What do you want as the final output? (report, analysis, code, etc.)</li>
          </ul>
        </div>
        
        <div class="form-examples">
          <h3 class="examples-title">Example Requests</h3>
          <div class="examples-grid">
            <button type="button" class="example-card" data-example="research">
              <div class="example-title">Research & Analysis</div>
              <div class="example-text">Research market trends and create analysis report</div>
            </button>
            <button type="button" class="example-card" data-example="coding">
              <div class="example-title">Code & Development</div>
              <div class="example-text">Build a data processing script with visualizations</div>
            </button>
            <button type="button" class="example-card" data-example="mixed">
              <div class="example-title">Mixed Workflow</div>
              <div class="example-text">Research, analyze data, and create presentation</div>
            </button>
          </div>
        </div>
      </div>
    `;

        // Cache DOM references
        this.form = this.element.querySelector('#request-form');
        this.textarea = this.element.querySelector('#request-input');
        this.submitButton = this.element.querySelector('#submit-button');
        this.clearButton = this.element.querySelector('#clear-button');
        this.termsCheckbox = this.element.querySelector('#terms-checkbox');
        this.charCounter = this.element.querySelector('#char-count');
        this.requestError = this.element.querySelector('#request-error');
        this.termsError = this.element.querySelector('#terms-error');
    }

    setupEventListeners() {
        // Form submission
        this.form.addEventListener('submit', (e) => this.handleSubmit(e));

        // Clear button
        this.clearButton.addEventListener('click', () => this.clearForm());

        // Real-time validation
        this.textarea.addEventListener('input', () => this.handleInput());
        this.textarea.addEventListener('blur', () => this.validateRequest());
        this.termsCheckbox.addEventListener('change', () => {
            this.validateTerms();
            this.validateForm(); // Update button state when checkbox changes
        });

        // Example cards
        this.element.querySelectorAll('.example-card').forEach(card => {
            card.addEventListener('click', (e) => this.handleExampleClick(e));
        });

        // Keyboard shortcuts
        this.textarea.addEventListener('keydown', (e) => this.handleKeydown(e));
    }

    setupValidation() {
        // Initialize character counter
        this.updateCharCounter();

        // Set initial validation state
        this.validateForm();
    }

    handleInput() {
        this.updateCharCounter();
        this.clearError('request');

        // Immediate validation for button state (no debounce for better UX)
        this.validateForm();

        // Debounced validation for error messages
        clearTimeout(this.validationTimeout);
        this.validationTimeout = setTimeout(() => {
            this.validateRequest();
        }, 500);
    }

    handleKeydown(e) {
        // Ctrl/Cmd + Enter to submit
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            if (this.validateForm()) {
                this.handleSubmit(e);
            }
        }
    }

    handleExampleClick(e) {
        const exampleType = e.currentTarget.dataset.example;
        const examples = {
            research: 'Research the latest developments in artificial intelligence, analyze the impact on job markets, and create a comprehensive report with recommendations for businesses preparing for AI adoption.',
            coding: 'Create a Python script that generates sample sales data, performs statistical analysis to identify trends, creates visualizations showing monthly patterns, and calculates key performance metrics with insights.',
            mixed: 'Research sustainable energy solutions for small businesses, analyze cost-benefit ratios, create financial projections, and develop a presentation for stakeholders with implementation recommendations.'
        };

        if (examples[exampleType]) {
            this.textarea.value = examples[exampleType];
            this.updateCharCounter();
            this.validateRequest();
            this.validateForm(); // Update button state after setting example text

            // Trigger input event to ensure all validation flows work
            this.textarea.dispatchEvent(new Event('input', { bubbles: true }));

            this.textarea.focus();
        }
    }

    async handleSubmit(e) {
        e.preventDefault();

        if (!this.validateForm()) {
            return;
        }

        const request = this.textarea.value.trim();

        try {
            this.setLoadingState(true);

            // Submit request through API service
            const response = await this.apiService.submitRequest(request);

            if (response.success) {
                // Clear form on successful submission
                this.clearForm();

                // Show success feedback
                this.showSuccessMessage('Request submitted successfully! Creating execution plan...');

            } else {
                throw new Error(response.error || 'Failed to submit request');
            }

        } catch (error) {
            console.error('Request submission failed:', error);

            // Provide user-friendly error messages based on error type
            let errorMessage = 'Failed to submit request. Please try again.';

            if (error.message.includes('422') || error.message.includes('Unprocessable Entity')) {
                errorMessage = 'Please provide a more detailed and specific request. Try describing a concrete task, project, or problem you need help with. For example: "Research market trends for electric vehicles and create a business analysis report."';
            } else if (error.message.includes('400')) {
                errorMessage = 'Invalid request format. Please check your input and try again.';
            } else if (error.message.includes('429')) {
                errorMessage = 'Too many requests. Please wait a moment before trying again.';
            } else if (error.message.includes('500')) {
                errorMessage = 'Server error. Please try again in a few moments.';
            } else if (error.message.includes('timeout') || error.message.includes('network')) {
                errorMessage = 'Connection timeout. Please check your internet connection and try again.';
            }

            this.showError('request', errorMessage);
        } finally {
            this.setLoadingState(false);
        }
    }

    validateForm() {
        const isRequestValid = this.validateRequest();
        const areTermsValid = this.validateTerms();

        const isValid = isRequestValid && areTermsValid;

        // Debug logging
        console.log('Form validation:', {
            isRequestValid,
            areTermsValid,
            isValid,
            textLength: this.textarea.value.trim().length,
            checkboxChecked: this.termsCheckbox.checked
        });

        // Update submit button state
        this.submitButton.disabled = !isValid;

        return isValid;
    }

    validateRequest() {
        const value = this.textarea.value.trim();
        const length = value.length;

        if (length === 0) {
            this.showError('request', 'Please describe your task or project');
            return false;
        }

        if (length < this.config.minLength) {
            this.showError('request', `Please provide more detail (minimum ${this.config.minLength} characters)`);
            return false;
        }

        if (length > this.config.maxLength) {
            this.showError('request', `Request is too long (maximum ${this.config.maxLength} characters)`);
            return false;
        }

        // Check for meaningful content (not just whitespace/repeated characters)
        if (!/\w+.*\w+.*\w+/.test(value)) {
            this.showError('request', 'Please provide a more detailed description');
            return false;
        }

        // Check for very short or vague requests
        const words = value.split(/\s+/).filter(word => word.length > 2);
        if (words.length < 5) {
            this.showError('request', 'Please provide more detail about what you want to accomplish');
            return false;
        }

        // Check for common invalid patterns
        const invalidPatterns = [
            /^(hi|hello|hey|test|testing)(\s|$)/i,
            /^(how are you|what's up|sup)(\s|$)/i,
            /^(asdf|qwerty|123|abc)/i,
            /^(.)\1{5,}/, // Repeated characters like "aaaaaaa"
        ];

        for (const pattern of invalidPatterns) {
            if (pattern.test(value)) {
                this.showError('request', 'Please describe a specific task or project you need help with. For example: "Research renewable energy trends and create a market analysis report."');
                return false;
            }
        }

        this.clearError('request');
        return true;
    }

    validateTerms() {
        if (!this.termsCheckbox.checked) {
            this.showError('terms', 'Please acknowledge the terms to continue');
            return false;
        }

        this.clearError('terms');
        return true;
    }

    updateCharCounter() {
        const length = this.textarea.value.length;
        this.charCounter.textContent = length;

        // Update counter styling based on length
        this.charCounter.className = '';
        if (length > this.config.maxLength * 0.9) {
            this.charCounter.classList.add('char-counter-warning');
        } else if (length > this.config.maxLength) {
            this.charCounter.classList.add('char-counter-error');
        }
    }

    showError(field, message) {
        const errorElement = field === 'request' ? this.requestError : this.termsError;
        const inputElement = field === 'request' ? this.textarea : this.termsCheckbox;

        errorElement.textContent = message;
        errorElement.style.display = 'block';
        inputElement.classList.add('error');

        // Accessibility: announce error to screen readers
        errorElement.setAttribute('aria-live', 'polite');
    }

    clearError(field) {
        const errorElement = field === 'request' ? this.requestError : this.termsError;
        const inputElement = field === 'request' ? this.textarea : this.termsCheckbox;

        errorElement.textContent = '';
        errorElement.style.display = 'none';
        inputElement.classList.remove('error');
    }

    showSuccessMessage(message) {
        // Create temporary success message
        const successElement = DOMUtils.createElement('div', 'form-success');
        successElement.textContent = message;
        successElement.setAttribute('role', 'status');
        successElement.setAttribute('aria-live', 'polite');

        this.form.insertBefore(successElement, this.form.firstChild);

        // Remove after 5 seconds
        setTimeout(() => {
            if (successElement.parentNode) {
                successElement.parentNode.removeChild(successElement);
            }
        }, 5000);
    }

    setLoadingState(loading) {
        const btnText = this.submitButton.querySelector('.btn-text');
        const btnLoading = this.submitButton.querySelector('.btn-loading');

        if (loading) {
            btnText.style.display = 'none';
            btnLoading.style.display = 'flex';
            this.submitButton.disabled = true;
            this.textarea.disabled = true;
            this.clearButton.disabled = true;
            this.termsCheckbox.disabled = true;
        } else {
            btnText.style.display = 'block';
            btnLoading.style.display = 'none';
            this.submitButton.disabled = false;
            this.textarea.disabled = false;
            this.clearButton.disabled = false;
            this.termsCheckbox.disabled = false;
        }
    }

    clearForm() {
        this.textarea.value = '';
        this.termsCheckbox.checked = false;
        this.updateCharCounter();
        this.clearError('request');
        this.clearError('terms');
        this.validateForm();
        this.textarea.focus();
    }

    // Public methods for external control
    setValue(value) {
        this.textarea.value = value;
        this.updateCharCounter();
        this.validateRequest();
    }

    getValue() {
        return this.textarea.value.trim();
    }

    focus() {
        this.textarea.focus();
    }

    render() {
        return this.element;
    }

    destroy() {
        if (this.validationTimeout) {
            clearTimeout(this.validationTimeout);
        }

        if (this.element && this.element.parentNode) {
            this.element.parentNode.removeChild(this.element);
        }
    }
}