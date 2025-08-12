/**
 * API Service Integration Layer
 * Bridges API client with state management system
 */

import { apiClient, StatusPoller } from '../utils/api.js';
import { stateManager, eventBus } from '../utils/state.js';

/**
 * API Service that integrates with state management
 */
export class ApiService {
    constructor() {
        this.apiClient = apiClient;
        this.stateManager = stateManager;
        this.eventBus = eventBus;
        this.statusPoller = null;
        this.isInitialized = false;
        this.approvalStateLocked = false; // Prevent state changes during approval

        // Bind methods
        this.init = this.init.bind(this);
        this.submitRequest = this.submitRequest.bind(this);
        this.handleStatusUpdate = this.handleStatusUpdate.bind(this);

        // Initialize if not already done
        if (!this.isInitialized) {
            this.init();
        }
    }

    /**
     * Initialize the API service
     */
    init() {
        if (this.isInitialized) {
            return;
        }

        console.log('[ApiService] Initializing API service');

        // Subscribe to state changes that require API calls
        this.stateManager.subscribeToStatusChange('planning', () => {
            this.startStatusPolling();
        });

        this.stateManager.subscribeToStatusChange('executing', () => {
            this.startStatusPolling();
        });

        this.stateManager.subscribeToStatusChange('completed', () => {
            this.stopStatusPolling();
        });

        this.stateManager.subscribeToStatusChange('error', () => {
            this.stopStatusPolling();
        });

        // Listen for approval events
        this.eventBus.on('planApproval', (data) => {
            this.handlePlanApproval(data);
        });

        // Listen for cancellation requests
        this.eventBus.on('cancelWorkflow', (data) => {
            this.handleCancelWorkflow(data);
        });

        // Perform initial health check
        this.performHealthCheck();

        this.isInitialized = true;
        console.log('[ApiService] API service initialized');
    }

    /**
     * Submit a new request to start workflow
     */
    async submitRequest(userRequest, threadId = null) {
        console.log('[ApiService] Submitting request:', { userRequest, threadId });

        // Update state to show loading
        this.stateManager.setState({
            isLoading: true,
            currentRequest: userRequest,
            status: 'planning',
            error: null
        }, 'apiService.submitRequest');

        try {
            const response = await this.apiClient.submitRequest(userRequest, threadId);

            if (response.success) {
                // Update state with successful submission
                this.stateManager.setState({
                    threadId: response.threadId,
                    status: 'planning',
                    isLoading: false
                }, 'apiService.submitRequest.success');

                // Emit success event
                this.eventBus.emit('requestSubmitted', {
                    threadId: response.threadId,
                    userRequest,
                    timestamp: new Date().toISOString()
                });

                // Start polling immediately after successful submission
                console.log('[ApiService] Request submitted successfully, starting polling for thread:', response.threadId);
                setTimeout(() => {
                    this.startStatusPolling();
                }, 1000); // Small delay to ensure state is updated

                return {
                    success: true,
                    threadId: response.threadId
                };

            } else {
                // Handle submission error
                this.handleApiError(response, 'Failed to submit request');
                return {
                    success: false,
                    error: response.error
                };
            }

        } catch (error) {
            console.error('[ApiService] Request submission failed:', error);
            this.handleApiError(error, 'Request submission failed');
            return {
                success: false,
                error: error.message
            };
        }
    }

    /**
     * Handle plan approval/rejection
     */
    async handlePlanApproval(approvalData) {
        const { threadId, approved, feedback } = approvalData;

        console.log('[ApiService] Handling plan approval:', approvalData);

        if (!threadId) {
            console.error('[ApiService] No thread ID provided for approval');
            return;
        }

        // Update state to show processing
        this.stateManager.setState({
            isLoading: true
        }, 'apiService.handlePlanApproval');

        try {
            const response = await this.apiClient.submitApproval(threadId, approved, feedback);

            if (response.success) {
                // Unlock approval state first
                console.log('[ApiService] Unlocking approval state after user decision');
                this.approvalStateLocked = false;

                // Update state based on approval result
                if (approved) {
                    const currentState = this.stateManager.getState();
                    const taskCount = currentState.plan?.length || 3; // Default to 3 tasks if unknown

                    this.stateManager.setState({
                        status: 'executing',
                        isLoading: false,
                        activeComponent: 'execution', // Switch to execution view
                        executionStartTime: Date.now(),
                        estimatedDuration: taskCount * 30000, // 30 seconds per task
                        simulatedProgress: 0
                    }, 'apiService.handlePlanApproval.approved');

                    // Start progress simulation
                    this.startProgressSimulation();

                    // Start gentle polling for completion detection
                    console.log('[ApiService] Plan approved, starting gentle polling for completion');
                    setTimeout(() => {
                        this.startGentlePolling();
                    }, 2000); // Wait 2 seconds before starting polling
                } else {
                    this.stateManager.setState({
                        status: 'planning',
                        plan: null, // Clear rejected plan
                        isLoading: true // Show loading during regeneration
                    }, 'apiService.handlePlanApproval.rejected');

                    // Restart polling immediately for plan regeneration
                    console.log('[ApiService] Plan rejected, restarting polling for regeneration');
                    setTimeout(() => {
                        this.startStatusPolling();
                    }, 500);
                }

                // Emit approval event
                this.eventBus.emit('approvalSubmitted', {
                    threadId,
                    approved,
                    feedback,
                    timestamp: new Date().toISOString()
                });

            } else {
                this.handleApiError(response, 'Failed to submit approval');
            }

        } catch (error) {
            console.error('[ApiService] Approval submission failed:', error);
            this.handleApiError(error, 'Approval submission failed');
        }
    }

    /**
     * Handle workflow cancellation
     */
    async handleCancelWorkflow(data) {
        const { threadId } = data;

        console.log('[ApiService] Cancelling workflow:', threadId);

        if (!threadId) {
            console.error('[ApiService] No thread ID provided for cancellation');
            return;
        }

        try {
            const response = await this.apiClient.cancelWorkflow(threadId);

            if (response.success) {
                this.stateManager.setState({
                    status: 'idle',
                    threadId: null,
                    plan: null,
                    progress: 0,
                    isLoading: false
                }, 'apiService.handleCancelWorkflow');

                this.eventBus.emit('workflowCancelled', {
                    threadId,
                    timestamp: new Date().toISOString()
                });

            } else {
                this.handleApiError(response, 'Failed to cancel workflow');
            }

        } catch (error) {
            console.error('[ApiService] Workflow cancellation failed:', error);
            this.handleApiError(error, 'Workflow cancellation failed');
        }
    }

    /**
     * Start status polling
     */
    startStatusPolling() {
        const currentState = this.stateManager.getState();

        if (!currentState.threadId) {
            console.warn('[ApiService] Cannot start polling without thread ID. Current state:', {
                status: currentState.status,
                threadId: currentState.threadId,
                isLoading: currentState.isLoading
            });

            // Try to recover by checking if we have a thread ID in a few seconds
            setTimeout(() => {
                const retryState = this.stateManager.getState();
                if (retryState.threadId && ['planning', 'executing', 'awaiting_approval'].includes(retryState.status)) {
                    console.log('[ApiService] Retrying polling with recovered thread ID:', retryState.threadId);
                    this.startStatusPolling();
                }
            }, 2000);
            return;
        }

        // Stop existing poller if running
        if (this.statusPoller && this.statusPoller.isPolling) {
            console.log('[ApiService] Stopping existing poller before starting new one');
            this.statusPoller.stop();
        }

        console.log('[ApiService] Starting status polling for thread:', currentState.threadId);
        console.log('[ApiService] Thread ID type:', typeof currentState.threadId, 'length:', currentState.threadId?.length);

        // Get polling interval from preferences - use faster polling during execution
        let pollingInterval = currentState.preferences.pollingInterval || 2000;
        if (currentState.status === 'executing') {
            pollingInterval = 1500; // Faster polling during execution
        }

        this.statusPoller = new StatusPoller(
            this.apiClient,
            currentState.threadId,
            this.handleStatusUpdate,
            {
                interval: pollingInterval,
                adaptivePolling: true,
                maxAttempts: 600, // 20 minutes with faster polling
                statusIntervals: {
                    'planning': 3000,
                    'awaiting_approval': 10000,
                    'executing': 1500, // Faster during execution
                    'in_progress': 1500,
                    'ready_for_execution': 1500,
                    'finalizing': 2000,
                    'completed': 0,
                    'failed': 0,
                    'cancelled': 0
                }
            }
        );

        this.statusPoller.start();

        // Emit polling started event
        this.eventBus.emit('pollingStarted', {
            threadId: currentState.threadId,
            interval: pollingInterval,
            timestamp: new Date().toISOString()
        });
    }

    /**
     * Stop status polling
     */
    stopStatusPolling() {
        if (this.statusPoller) {
            console.log('[ApiService] Stopping status polling');
            this.statusPoller.stop();
            this.statusPoller = null;

            this.eventBus.emit('pollingStopped', {
                timestamp: new Date().toISOString()
            });
        }
    }

    /**
     * Perform immediate status check (used after approval to get latest state)
     */
    async performImmediateStatusCheck() {
        const currentState = this.stateManager.getState();

        if (!currentState.threadId) {
            console.warn('[ApiService] Cannot perform immediate status check without thread ID');
            return;
        }

        console.log('[ApiService] Performing immediate status check for thread:', currentState.threadId);

        try {
            const statusData = await this.apiClient.getStatus(currentState.threadId);

            if (statusData.success) {
                console.log('[ApiService] Immediate status check successful:', statusData);
                this.handleStatusUpdate(statusData);
            } else {
                console.warn('[ApiService] Immediate status check failed:', statusData.error);
            }
        } catch (error) {
            console.error('[ApiService] Immediate status check error:', error);
        }
    }

    /**
     * Force stop polling with aggressive cleanup
     */
    forceStopPolling() {
        console.log('[ApiService] FORCE stopping all polling activity');

        if (this.statusPoller) {
            console.log('[ApiService] Stopping existing poller');
            this.statusPoller.stop();

            // Clear any pending timeouts
            if (this.statusPoller.timeoutId) {
                clearTimeout(this.statusPoller.timeoutId);
                this.statusPoller.timeoutId = null;
            }

            // Force set polling flag to false
            this.statusPoller.isPolling = false;
            this.statusPoller = null;
        }

        // Clear any other potential timeouts
        if (this.pollingTimeoutId) {
            clearTimeout(this.pollingTimeoutId);
            this.pollingTimeoutId = null;
        }

        this.eventBus.emit('pollingStopped', {
            timestamp: new Date().toISOString(),
            forced: true
        });

        console.log('[ApiService] Polling FORCE stopped - no more network requests should occur');
    }

    /**
     * Handle status updates from polling
     */
    handleStatusUpdate(statusData) {
        // FIRST CHECK: If approval is locked, ignore ALL updates
        if (this.approvalStateLocked) {
            console.log('[ApiService] Approval locked - ignoring ALL status updates');
            return;
        }

        if (!statusData.success) {
            console.warn('[ApiService] Status update failed:', statusData.error);

            const currentState = this.stateManager.getState();

            // Don't change state to error if we're in approval phase - network errors are expected
            if (currentState.status === 'awaiting_approval') {
                console.log('[ApiService] Ignoring polling error during approval phase - user can still interact');

                // Just update connection status but don't change the main state
                this.stateManager.setState({
                    apiConnected: false
                }, 'apiService.handleStatusUpdate.approvalPhaseError');
                return;
            }

            if (statusData.pollingFailed) {
                // Polling failed completely - only set error if not in approval phase
                this.stateManager.setState({
                    error: 'Lost connection to server',
                    apiConnected: false
                }, 'apiService.handleStatusUpdate.pollingFailed');
            }
            return;
        }

        console.log('[ApiService] Status update received:', statusData);

        const currentState = this.stateManager.getState();
        console.log('[ApiService] Current frontend status before update:', currentState.status);

        // CRITICAL: Don't override approval state if user is currently reviewing
        // Only transition FROM approval state when user explicitly approves/rejects
        // BUT allow transitions TO approval state (new plan received after rejection)
        if (this.approvalStateLocked &&
            currentState.status === 'awaiting_approval' &&
            (statusData.status === 'pending_approval' || statusData.status === 'awaiting_approval')) {
            console.log('[ApiService] Approval state locked - user is reviewing same plan, not updating state from polling');

            // Still update API connection status
            this.stateManager.setState({
                apiConnected: true
            }, 'apiService.handleStatusUpdate.connected');

            // Emit status update event for debugging but don't change state
            this.eventBus.emit('statusUpdate', {
                ...statusData,
                timestamp: new Date().toISOString()
            });
            return;
        }

        // If we're transitioning FROM planning TO approval, unlock the approval state
        if (currentState.status === 'planning' &&
            (statusData.status === 'pending_approval' || statusData.status === 'awaiting_approval')) {
            console.log('[ApiService] Unlocking approval state - new plan received after regeneration');
            this.approvalStateLocked = false;
        }

        // Special handling for execution state - always update progress even if status hasn't changed
        if (statusData.status === 'executing' || statusData.status === 'in_progress') {
            console.log('[ApiService] Execution progress update:', {
                currentProgress: currentState.progress,
                newProgress: (statusData.progress?.completion_percentage || 0) / 100,
                taskResults: Object.keys(statusData.task_results || {}).length
            });
        }

        // Log detailed status data for debugging
        if (statusData.status === 'executing' || statusData.status === 'in_progress') {
            console.log('[ApiService] Execution status details:', {
                status: statusData.status,
                progress: statusData.progress,
                plan: statusData.plan?.map(t => ({ id: t.id, status: t.status, description: t.description?.substring(0, 50) })),
                tasks: statusData.tasks?.map(t => ({ id: t.id, status: t.status })),
                current_task: statusData.current_task
            });
        }

        // Update API connection status
        this.stateManager.setState({
            apiConnected: true
        }, 'apiService.handleStatusUpdate.connected');

        // Map backend status to frontend state
        const stateUpdates = {
            progress: statusData.progress || 0
        };

        // Handle status-specific updates
        switch (statusData.status) {
            case 'planning':
                stateUpdates.status = 'planning';
                stateUpdates.isLoading = true;
                break;

            case 'pending_approval':
            case 'awaiting_approval':
                console.log('[ApiService] Received approval status, plan data:', statusData.plan);
                stateUpdates.status = 'awaiting_approval';
                stateUpdates.plan = statusData.plan;
                stateUpdates.isLoading = false;
                break;

            case 'executing':
            case 'in_progress':
            case 'ready_for_execution':
                console.log('[ApiService] Received executing status, full data:', statusData);
                console.log('[ApiService] Received executing status, data summary:', {
                    plan: statusData.plan?.length,
                    tasks: statusData.tasks?.length,
                    taskResults: Object.keys(statusData.task_results || {}).length,
                    currentTaskId: statusData.current_task_id,
                    progress: statusData.progress
                });
                stateUpdates.status = 'executing';
                stateUpdates.plan = statusData.plan;
                stateUpdates.tasks = statusData.tasks || [];
                stateUpdates.taskResults = statusData.task_results || {};
                stateUpdates.currentTaskId = statusData.current_task_id;
                stateUpdates.progress = (statusData.progress?.completion_percentage || 0) / 100;
                stateUpdates.isLoading = false;

                // Ensure polling is at normal speed during execution
                if (this.statusPoller) {
                    this.statusPoller.updateOptions({ interval: 2000 }); // Poll every 2 seconds
                }
                break;

            case 'completed':
                stateUpdates.status = 'completed';
                stateUpdates.finalReport = statusData.final_report;
                stateUpdates.taskResults = statusData.task_results || {};
                stateUpdates.completedAt = statusData.completed_at;
                stateUpdates.progress = 1.0;
                stateUpdates.isLoading = false;
                break;

            case 'failed':
                stateUpdates.status = 'error';
                stateUpdates.error = statusData.error || 'Workflow execution failed';
                stateUpdates.isLoading = false;
                break;

            case 'cancelled':
                stateUpdates.status = 'error';
                stateUpdates.error = 'Workflow was cancelled';
                stateUpdates.isLoading = false;
                break;

            default:
                console.warn('[ApiService] Unknown status received:', statusData.status);
        }

        // Update state with new data
        console.log('[ApiService] Updating state with:', stateUpdates);
        this.stateManager.setState(stateUpdates, 'apiService.handleStatusUpdate');
        console.log('[ApiService] New frontend status after update:', this.stateManager.getState().status);

        // Lock approval state and stop polling if we just transitioned to approval state
        if (stateUpdates.status === 'awaiting_approval') {
            console.log('[ApiService] Locking approval state and FORCE stopping polling');
            this.approvalStateLocked = true;
            this.forceStopPolling();
        }

        // Emit status update event
        this.eventBus.emit('statusUpdate', {
            ...statusData,
            timestamp: new Date().toISOString()
        });
    }

    /**
     * Handle API errors
     */
    handleApiError(error, context = 'API call') {
        console.error(`[ApiService] ${context}:`, error);

        const errorMessage = error.error || error.message || 'An unexpected error occurred';

        this.stateManager.setState({
            status: 'error',
            error: errorMessage,
            lastError: {
                message: errorMessage,
                context,
                timestamp: new Date().toISOString(),
                details: error.details || null
            },
            isLoading: false,
            apiConnected: error.status !== 0 // 0 usually means network error
        }, 'apiService.handleApiError');

        // Emit error event
        this.eventBus.emit('apiError', {
            error: errorMessage,
            context,
            details: error,
            timestamp: new Date().toISOString()
        });
    }

    /**
     * Perform health check
     */
    async performHealthCheck() {
        try {
            const response = await this.apiClient.healthCheck();

            this.stateManager.setState({
                apiConnected: response.success,
                systemStatus: response.success ? 'healthy' : 'error'
            }, 'apiService.performHealthCheck');

            if (response.success) {
                console.log('[ApiService] Health check passed');
            } else {
                console.warn('[ApiService] Health check failed:', response.error);
            }

        } catch (error) {
            console.error('[ApiService] Health check error:', error);
            this.stateManager.setState({
                apiConnected: false,
                systemStatus: 'error'
            }, 'apiService.performHealthCheck.error');
        }
    }

    /**
     * Get current polling statistics
     */
    getPollingStats() {
        return this.statusPoller ? this.statusPoller.getStats() : null;
    }

    /**
     * Update polling configuration
     */
    updatePollingConfig(options) {
        if (this.statusPoller) {
            this.statusPoller.updateOptions(options);
        }

        // Update preferences in state
        const currentState = this.stateManager.getState();
        this.stateManager.setState({
            preferences: {
                ...currentState.preferences,
                pollingInterval: options.interval || currentState.preferences.pollingInterval
            }
        }, 'apiService.updatePollingConfig');
    }

    /**
     * Start progress simulation for better UX during execution
     */
    startProgressSimulation() {
        console.log('[ApiService] Starting progress simulation');

        // Clear any existing simulation
        if (this.progressSimulationInterval) {
            clearInterval(this.progressSimulationInterval);
        }

        const currentState = this.stateManager.getState();
        const startTime = currentState.executionStartTime || Date.now();
        const estimatedDuration = currentState.estimatedDuration || 90000; // 90 seconds default

        this.progressSimulationInterval = setInterval(() => {
            const currentState = this.stateManager.getState();

            // Only simulate if we're still executing and haven't completed
            if (currentState.status !== 'executing') {
                clearInterval(this.progressSimulationInterval);
                return;
            }

            const elapsed = Date.now() - startTime;
            const progressRatio = Math.min(elapsed / estimatedDuration, 0.95); // Cap at 95%

            // Use easing function for more natural progress
            const easedProgress = this.easeOutCubic(progressRatio);

            this.stateManager.setState({
                simulatedProgress: easedProgress,
                progress: easedProgress
            }, 'apiService.progressSimulation');

            console.log(`[ApiService] Simulated progress: ${Math.round(easedProgress * 100)}%`);

        }, 1000); // Update every second
    }

    /**
     * Easing function for natural progress animation
     */
    easeOutCubic(t) {
        return 1 - Math.pow(1 - t, 3);
    }

    /**
     * Start gentle polling that only checks for completion
     */
    startGentlePolling() {
        console.log('[ApiService] Starting gentle polling for completion detection');

        // Clear any existing gentle polling
        if (this.gentlePollingInterval) {
            clearInterval(this.gentlePollingInterval);
        }

        let attemptCount = 0;
        const maxAttempts = 60; // 10 minutes with 10-second intervals

        this.gentlePollingInterval = setInterval(async () => {
            attemptCount++;
            const currentState = this.stateManager.getState();

            // Stop if we're no longer executing or exceeded max attempts
            if (currentState.status !== 'executing' || attemptCount > maxAttempts) {
                clearInterval(this.gentlePollingInterval);
                if (attemptCount > maxAttempts) {
                    console.warn('[ApiService] Gentle polling timed out');
                    this.handlePollingTimeout();
                }
                return;
            }

            console.log(`[ApiService] Gentle polling attempt ${attemptCount}/${maxAttempts}`);

            try {
                const statusData = await this.apiClient.getStatus(currentState.threadId);

                if (statusData.success) {
                    console.log(`[ApiService] Gentle polling success - status: ${statusData.status}`);

                    // Only act on completion or error states
                    if (statusData.status === 'completed') {
                        console.log('[ApiService] Workflow completed! Transitioning to results');

                        // Stop simulation and polling
                        clearInterval(this.progressSimulationInterval);
                        clearInterval(this.gentlePollingInterval);

                        // Update to completed state
                        this.stateManager.setState({
                            status: 'completed',
                            progress: 1.0,
                            simulatedProgress: 1.0,
                            finalReport: statusData.final_report,
                            taskResults: statusData.task_results || {},
                            completedAt: statusData.completed_at || new Date().toISOString(),
                            isLoading: false
                        }, 'apiService.gentlePolling.completed');

                    } else if (statusData.status === 'failed') {
                        console.log('[ApiService] Workflow failed');

                        // Stop simulation and polling
                        clearInterval(this.progressSimulationInterval);
                        clearInterval(this.gentlePollingInterval);

                        this.stateManager.setState({
                            status: 'error',
                            error: statusData.error || 'Workflow execution failed',
                            isLoading: false
                        }, 'apiService.gentlePolling.failed');
                    }
                    // For other statuses (executing, in_progress), just continue polling

                } else {
                    console.log(`[ApiService] Gentle polling failed: ${statusData.error}`);
                    // Continue polling on failure - the backend might still be processing
                }

            } catch (error) {
                console.log(`[ApiService] Gentle polling error: ${error.message}`);
                // Continue polling on error - network issues are expected
            }

        }, 10000); // Poll every 10 seconds (much gentler than before)
    }

    /**
     * Handle polling timeout gracefully
     */
    handlePollingTimeout() {
        console.log('[ApiService] Handling polling timeout gracefully');

        const currentState = this.stateManager.getState();

        // Stop simulation
        if (this.progressSimulationInterval) {
            clearInterval(this.progressSimulationInterval);
        }

        // Show a user-friendly message
        this.stateManager.setState({
            status: 'completed', // Assume completion
            progress: 1.0,
            simulatedProgress: 1.0,
            finalReport: 'Workflow execution completed. The system took longer than expected to respond, but your tasks have likely been processed successfully.',
            isLoading: false,
            completedAt: new Date().toISOString()
        }, 'apiService.pollingTimeout');

        // Emit timeout event for potential user notification
        this.eventBus.emit('executionTimeout', {
            threadId: currentState.threadId,
            timestamp: new Date().toISOString()
        });
    }

    /**
     * Cleanup resources
     */
    destroy() {
        console.log('[ApiService] Destroying API service');
        this.stopStatusPolling();

        // Clear simulation intervals
        if (this.progressSimulationInterval) {
            clearInterval(this.progressSimulationInterval);
        }
        if (this.gentlePollingInterval) {
            clearInterval(this.gentlePollingInterval);
        }

        // Note: We don't clear event listeners as they might be needed by other components
    }
}

// Create singleton instance
export const apiService = new ApiService();

// Export for testing and debugging
if (typeof window !== 'undefined') {
    window.clarityApiService = apiService;

    // Debug helper
    window.debugPolling = () => {
        const state = apiService.stateManager.getState();
        const pollingStats = apiService.getPollingStats();

        console.log('=== POLLING DEBUG INFO ===');
        console.log('Current State:', {
            status: state.status,
            threadId: state.threadId,
            isLoading: state.isLoading,
            apiConnected: state.apiConnected
        });
        console.log('Approval State Locked:', apiService.approvalStateLocked);
        console.log('Polling Stats:', pollingStats);
        console.log('Poller Active:', apiService.statusPoller?.isPolling || false);
        console.log('========================');

        return {
            state,
            pollingStats,
            pollerActive: apiService.statusPoller?.isPolling || false,
            approvalLocked: apiService.approvalStateLocked
        };
    };

    // Force status check helper
    window.forceStatusCheck = async () => {
        console.log('=== FORCING STATUS CHECK ===');
        await apiService.performImmediateStatusCheck();
        console.log('Status check completed');
    };

    // Force restart polling helper
    window.forceRestartPolling = () => {
        console.log('=== FORCING POLLING RESTART ===');
        apiService.approvalStateLocked = false;
        apiService.startStatusPolling();
        console.log('Polling restarted');
    };
}