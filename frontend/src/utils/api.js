/**
 * API Client for Clarity.ai Backend Communication
 * Handles all HTTP requests to the FastAPI backend with error handling and retry logic
 */

export class ApiClient {
    constructor(baseUrl = '/api/v1') {
        this.baseUrl = baseUrl;
        this.defaultTimeout = 30000; // 30 seconds
        this.retryAttempts = 3;
        this.retryDelay = 1000; // 1 second
    }

    /**
     * Generic HTTP request method with error handling and retry logic
     */
    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const config = {
            timeout: this.defaultTimeout,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        };

        let lastError;

        for (let attempt = 1; attempt <= this.retryAttempts; attempt++) {
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), config.timeout);

                const response = await fetch(url, {
                    ...config,
                    signal: controller.signal
                });

                clearTimeout(timeoutId);

                if (!response.ok) {
                    const errorData = await this.parseErrorResponse(response);
                    throw new ApiError(
                        errorData.message || `HTTP ${response.status}: ${response.statusText}`,
                        response.status,
                        errorData
                    );
                }

                const data = await response.json();
                return {
                    success: true,
                    data,
                    status: response.status,
                    headers: response.headers
                };

            } catch (error) {
                lastError = error;

                // Don't retry on client errors (4xx) or abort errors
                if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
                    break;
                }

                if (error.name === 'AbortError') {
                    lastError = new ApiError('Request timeout', 408);
                    break;
                }

                // Wait before retry (exponential backoff)
                if (attempt < this.retryAttempts) {
                    await this.delay(this.retryDelay * Math.pow(2, attempt - 1));
                }
            }
        }

        return {
            success: false,
            error: lastError.message || 'Request failed',
            status: lastError.status || 0,
            details: lastError.details
        };
    }

    /**
     * Parse error response from server
     */
    async parseErrorResponse(response) {
        try {
            const data = await response.json();
            return data;
        } catch {
            return {
                message: `HTTP ${response.status}: ${response.statusText}`,
                status: response.status
            };
        }
    }

    /**
     * Delay utility for retry logic
     */
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * Submit a new request to start workflow
     */
    async submitRequest(request, threadId = null) {
        const payload = {
            user_request: request.trim(),
            ...(threadId && { thread_id: threadId })
        };

        const response = await this.request('/run', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        if (response.success) {
            return {
                success: true,
                threadId: response.data.thread_id,
                status: response.data.status,
                message: response.data.message || 'Request submitted successfully'
            };
        }

        return response;
    }

    /**
     * Get workflow status and progress
     */
    async getStatus(threadId) {
        const response = await this.request(`/status/${threadId}`, {
            method: 'GET'
        });

        if (response.success) {
            return {
                success: true,
                ...response.data
            };
        }

        return response;
    }

    /**
     * Submit plan approval or rejection with feedback
     */
    async submitApproval(threadId, approved, feedback = null) {
        const payload = {
            approved,
            ...(feedback && { feedback: feedback.trim() })
        };

        const response = await this.request(`/approve/${threadId}`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        if (response.success) {
            return {
                success: true,
                message: response.data.message || 'Approval submitted successfully',
                status: response.data.status
            };
        }

        return response;
    }

    /**
     * Get workflow results
     */
    async getResults(threadId) {
        const response = await this.request(`/results/${threadId}`, {
            method: 'GET'
        });

        if (response.success) {
            return {
                success: true,
                results: response.data.results,
                finalReport: response.data.final_report,
                completedAt: response.data.completed_at
            };
        }

        return response;
    }

    /**
     * Cancel a running workflow
     */
    async cancelWorkflow(threadId) {
        const response = await this.request(`/cancel/${threadId}`, {
            method: 'POST'
        });

        if (response.success) {
            return {
                success: true,
                message: response.data.message || 'Workflow cancelled successfully'
            };
        }

        return response;
    }

    /**
     * Health check endpoint
     */
    async healthCheck() {
        const response = await this.request('/health', {
            method: 'GET',
            timeout: 5000 // Shorter timeout for health checks
        });

        return response;
    }

    /**
     * Get system status and metrics
     */
    async getSystemStatus() {
        const response = await this.request('/system/status', {
            method: 'GET'
        });

        if (response.success) {
            return {
                success: true,
                ...response.data
            };
        }

        return response;
    }
}

/**
 * Custom API Error class
 */
export class ApiError extends Error {
    constructor(message, status = 0, details = null) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.details = details;
    }
}

/**
 * Polling utility for status updates
 */
export class StatusPoller {
    constructor(apiClient, threadId, onUpdate, options = {}) {
        this.api = apiClient;
        this.threadId = threadId;
        this.onUpdate = onUpdate;
        this.options = {
            interval: 2000, // 2 seconds
            maxAttempts: 300, // 10 minutes max
            backoffMultiplier: 1.1,
            maxInterval: 10000, // 10 seconds max
            ...options
        };

        this.isPolling = false;
        this.attempts = 0;
        this.currentInterval = this.options.interval;
        this.timeoutId = null;
    }

    start() {
        if (this.isPolling) {
            return;
        }

        this.isPolling = true;
        this.attempts = 0;
        this.currentInterval = this.options.interval;
        this.poll();
    }

    stop() {
        this.isPolling = false;
        if (this.timeoutId) {
            clearTimeout(this.timeoutId);
            this.timeoutId = null;
        }
    }

    async poll() {
        if (!this.isPolling || this.attempts >= this.options.maxAttempts) {
            this.stop();
            return;
        }

        try {
            const status = await this.api.getStatus(this.threadId);

            if (status.success) {
                this.onUpdate(status);

                // Stop polling if workflow is complete or failed
                if (['completed', 'failed', 'cancelled'].includes(status.status)) {
                    this.stop();
                    return;
                }

                // Reset interval on successful request
                this.currentInterval = this.options.interval;
            } else {
                // Increase interval on error (exponential backoff)
                this.currentInterval = Math.min(
                    this.currentInterval * this.options.backoffMultiplier,
                    this.options.maxInterval
                );
            }

        } catch (error) {
            console.error('Polling error:', error);
            this.currentInterval = Math.min(
                this.currentInterval * this.options.backoffMultiplier,
                this.options.maxInterval
            );
        }

        this.attempts++;

        if (this.isPolling) {
            this.timeoutId = setTimeout(() => this.poll(), this.currentInterval);
        }
    }
}

// Export singleton instance
export const apiClient = new ApiClient();