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
     * Get or create a persistent user ID for tracking
     */
    getOrCreateUserId() {
        const storageKey = 'clarity_user_id';
        let userId = localStorage.getItem(storageKey);

        if (!userId) {
            // Generate a simple user ID
            userId = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
            localStorage.setItem(storageKey, userId);
        }

        return userId;
    }

    /**
     * Submit a new request to start workflow
     */
    async submitRequest(request, threadId = null, userId = null) {
        // Auto-generate persistent user ID if not provided
        if (!userId) {
            userId = this.getOrCreateUserId();
        }

        const payload = {
            user_request: request.trim(),
            ...(threadId && { thread_id: threadId }),
            ...(userId && { user_id: userId })
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
        try {
            const response = await this.request('/health', {
                method: 'GET',
                timeout: 5000 // Shorter timeout for health checks
            });

            return response;
        } catch (error) {
            console.error('[ApiClient] Health check failed:', error);
            return {
                success: false,
                error: error.message || 'Health check failed',
                status: error.status || 0
            };
        }
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
 * Enhanced Polling Service for Real-time Status Updates
 * Supports configurable intervals, intelligent backoff, and event-driven updates
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
            adaptivePolling: true, // Adjust interval based on status
            statusIntervals: {
                'planning': 3000,
                'awaiting_approval': 10000, // Slower when waiting for user
                'executing': 2000,
                'completed': 0, // Stop polling
                'failed': 0, // Stop polling
                'cancelled': 0 // Stop polling
            },
            ...options
        };

        this.isPolling = false;
        this.attempts = 0;
        this.currentInterval = this.options.interval;
        this.timeoutId = null;
        this.lastStatus = null;
        this.consecutiveErrors = 0;
        this.maxConsecutiveErrors = 10; // Increased tolerance for network issues

        // Performance tracking
        this.stats = {
            totalRequests: 0,
            successfulRequests: 0,
            failedRequests: 0,
            averageResponseTime: 0,
            startTime: null,
            lastRequestTime: null
        };
    }

    start() {
        if (this.isPolling) {
            console.warn('[StatusPoller] Already polling, ignoring start request');
            return;
        }

        console.log(`[StatusPoller] Starting polling for thread ${this.threadId}`);
        this.isPolling = true;
        this.attempts = 0;
        this.consecutiveErrors = 0;
        this.currentInterval = this.options.interval;
        this.stats.startTime = Date.now();
        this.poll();
    }

    stop() {
        if (!this.isPolling) {
            return;
        }

        console.log(`[StatusPoller] Stopping polling for thread ${this.threadId}`);
        this.isPolling = false;
        if (this.timeoutId) {
            clearTimeout(this.timeoutId);
            this.timeoutId = null;
        }

        // Log final stats
        this.logStats();
    }

    async poll() {
        if (!this.isPolling || this.attempts >= this.options.maxAttempts) {
            console.log(`[StatusPoller] Stopping: isPolling=${this.isPolling}, attempts=${this.attempts}/${this.options.maxAttempts}`);
            this.stop();
            return;
        }

        // Check if approval state is locked (global check)
        if (window.clarityApiService && window.clarityApiService.approvalStateLocked) {
            console.log('[StatusPoller] Approval state locked - stopping polling');
            this.stop();
            return;
        }

        const requestStart = Date.now();
        this.stats.totalRequests++;
        this.stats.lastRequestTime = requestStart;

        console.log(`[StatusPoller] Polling attempt ${this.attempts + 1} with thread ID: "${this.threadId}" (type: ${typeof this.threadId}, length: ${this.threadId?.length})`);

        try {
            const status = await this.api.getStatus(this.threadId);
            const responseTime = Date.now() - requestStart;

            // Update response time average
            this.stats.averageResponseTime = (
                (this.stats.averageResponseTime * (this.stats.successfulRequests)) + responseTime
            ) / (this.stats.successfulRequests + 1);

            if (status.success) {
                this.stats.successfulRequests++;
                this.consecutiveErrors = 0;

                console.log(`[StatusPoller] Poll successful - Status: ${status.status}, Progress: ${status.progress?.completion_percentage || 0}%`);

                // Call update handler
                this.onUpdate(status);

                // Check if we should stop polling
                if (this.shouldStopPolling(status.status)) {
                    console.log(`[StatusPoller] Stopping polling due to final status: ${status.status}`);
                    this.stop();
                    return;
                }

                // Adjust polling interval based on status
                this.adjustPollingInterval(status.status);
                this.lastStatus = status.status;

            } else {
                console.warn(`[StatusPoller] Poll failed with error: ${status.error}`);
                this.handlePollingError(new Error(status.error || 'Status request failed'));
            }

        } catch (error) {
            console.error(`[StatusPoller] Poll exception:`, error);
            this.handlePollingError(error);
        }

        this.attempts++;

        // Schedule next poll if still active
        if (this.isPolling) {
            console.log(`[StatusPoller] Scheduling next poll in ${this.currentInterval}ms`);
            this.timeoutId = setTimeout(() => this.poll(), this.currentInterval);
        }
    }

    /**
     * Handle polling errors with exponential backoff
     */
    handlePollingError(error) {
        this.stats.failedRequests++;
        this.consecutiveErrors++;

        console.error(`[StatusPoller] Polling error (${this.consecutiveErrors}/${this.maxConsecutiveErrors}):`, error);

        // Stop polling if too many consecutive errors
        if (this.consecutiveErrors >= this.maxConsecutiveErrors) {
            console.error('[StatusPoller] Too many consecutive errors, stopping polling');
            this.stop();

            // Notify about polling failure
            this.onUpdate({
                success: false,
                error: 'Polling failed due to repeated errors',
                pollingFailed: true
            });
            return;
        }

        // Increase interval on error (exponential backoff)
        this.currentInterval = Math.min(
            this.currentInterval * this.options.backoffMultiplier,
            this.options.maxInterval
        );
    }

    /**
     * Adjust polling interval based on current status
     */
    adjustPollingInterval(status) {
        if (!this.options.adaptivePolling) {
            return;
        }

        const statusInterval = this.options.statusIntervals[status];
        if (statusInterval !== undefined) {
            this.currentInterval = statusInterval;
        } else {
            // Reset to default interval for unknown statuses
            this.currentInterval = this.options.interval;
        }
    }

    /**
     * Check if polling should stop based on status
     */
    shouldStopPolling(status) {
        const finalStatuses = ['completed', 'failed', 'cancelled'];
        return finalStatuses.includes(status);
    }

    /**
     * Update polling configuration
     */
    updateOptions(newOptions) {
        this.options = { ...this.options, ...newOptions };
        console.log('[StatusPoller] Options updated:', this.options);
    }

    /**
     * Get current polling statistics
     */
    getStats() {
        const now = Date.now();
        const uptime = this.stats.startTime ? now - this.stats.startTime : 0;

        return {
            ...this.stats,
            uptime,
            isPolling: this.isPolling,
            currentInterval: this.currentInterval,
            consecutiveErrors: this.consecutiveErrors,
            successRate: this.stats.totalRequests > 0
                ? (this.stats.successfulRequests / this.stats.totalRequests) * 100
                : 0
        };
    }

    /**
     * Log polling statistics
     */
    logStats() {
        const stats = this.getStats();
        console.log('[StatusPoller] Final statistics:', {
            totalRequests: stats.totalRequests,
            successRate: `${stats.successRate.toFixed(1)}%`,
            averageResponseTime: `${stats.averageResponseTime.toFixed(0)}ms`,
            uptime: `${(stats.uptime / 1000).toFixed(1)}s`
        });
    }
}

// Export singleton instance
export const apiClient = new ApiClient();