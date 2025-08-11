/**
 * Centralized State Management System for Clarity.ai Frontend
 * Implements event-driven state management without framework dependencies
 */

/**
 * Custom Event System for Component Communication
 */
export class EventBus {
    constructor() {
        this.events = new Map();
        this.debugMode = false;
    }

    /**
     * Subscribe to an event
     * @param {string} eventName - Name of the event
     * @param {Function} callback - Callback function
     * @returns {Function} Unsubscribe function
     */
    on(eventName, callback) {
        if (!this.events.has(eventName)) {
            this.events.set(eventName, new Set());
        }

        this.events.get(eventName).add(callback);

        if (this.debugMode) {
            console.log(`[EventBus] Subscribed to '${eventName}'. Total listeners: ${this.events.get(eventName).size}`);
        }

        // Return unsubscribe function
        return () => this.off(eventName, callback);
    }

    /**
     * Unsubscribe from an event
     * @param {string} eventName - Name of the event
     * @param {Function} callback - Callback function to remove
     */
    off(eventName, callback) {
        if (this.events.has(eventName)) {
            this.events.get(eventName).delete(callback);

            if (this.debugMode) {
                console.log(`[EventBus] Unsubscribed from '${eventName}'. Remaining listeners: ${this.events.get(eventName).size}`);
            }

            // Clean up empty event sets
            if (this.events.get(eventName).size === 0) {
                this.events.delete(eventName);
            }
        }
    }

    /**
     * Emit an event to all subscribers
     * @param {string} eventName - Name of the event
     * @param {*} data - Data to pass to callbacks
     */
    emit(eventName, data) {
        if (this.debugMode) {
            console.log(`[EventBus] Emitting '${eventName}' with data:`, data);
        }

        if (this.events.has(eventName)) {
            const callbacks = this.events.get(eventName);
            callbacks.forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error(`[EventBus] Error in callback for '${eventName}':`, error);
                }
            });
        }
    }

    /**
     * Subscribe to an event only once
     * @param {string} eventName - Name of the event
     * @param {Function} callback - Callback function
     * @returns {Function} Unsubscribe function
     */
    once(eventName, callback) {
        const unsubscribe = this.on(eventName, (data) => {
            callback(data);
            unsubscribe();
        });
        return unsubscribe;
    }

    /**
     * Get all active event names
     * @returns {Array<string>} Array of event names
     */
    getEventNames() {
        return Array.from(this.events.keys());
    }

    /**
     * Get listener count for an event
     * @param {string} eventName - Name of the event
     * @returns {number} Number of listeners
     */
    getListenerCount(eventName) {
        return this.events.has(eventName) ? this.events.get(eventName).size : 0;
    }

    /**
     * Clear all events and listeners
     */
    clear() {
        this.events.clear();
        if (this.debugMode) {
            console.log('[EventBus] All events cleared');
        }
    }

    /**
     * Enable/disable debug mode
     * @param {boolean} enabled - Whether to enable debug mode
     */
    setDebugMode(enabled) {
        this.debugMode = enabled;
        console.log(`[EventBus] Debug mode ${enabled ? 'enabled' : 'disabled'}`);
    }
}

/**
 * Application State Manager
 * Manages centralized application state with reactive updates
 */
export class StateManager {
    constructor(eventBus) {
        this.eventBus = eventBus;
        this.state = this.getInitialState();
        this.history = [];
        this.maxHistorySize = 50;
        this.debugMode = false;

        // Bind methods to preserve context
        this.setState = this.setState.bind(this);
        this.getState = this.getState.bind(this);
        this.subscribe = this.subscribe.bind(this);
    }

    /**
     * Get initial application state
     * @returns {Object} Initial state object
     */
    getInitialState() {
        return {
            // Application status
            status: 'idle', // idle, planning, awaiting_approval, executing, completed, error

            // Current workflow data
            currentRequest: null,
            threadId: null,
            plan: null,
            progress: 0,

            // Task execution data
            tasks: [],
            taskResults: {},
            currentTaskId: null,

            // Results and completion
            finalReport: null,
            completedAt: null,

            // Error handling
            error: null,
            lastError: null,

            // UI state
            isLoading: false,
            activeComponent: 'input', // input, execution, approval, results

            // System state
            systemStatus: 'unknown', // healthy, degraded, error, unknown
            apiConnected: true,

            // User preferences
            preferences: {
                pollingInterval: 2000,
                enableNotifications: true,
                debugMode: false
            },

            // Metadata
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString()
        };
    }

    /**
     * Get current state (immutable copy)
     * @returns {Object} Current state
     */
    getState() {
        return JSON.parse(JSON.stringify(this.state));
    }

    /**
     * Update state with new values
     * @param {Object} updates - State updates to apply
     * @param {string} source - Source of the update (for debugging)
     */
    setState(updates, source = 'unknown') {
        if (typeof updates !== 'object' || updates === null) {
            console.error('[StateManager] setState called with invalid updates:', updates);
            return;
        }

        // Store previous state in history
        this.addToHistory(this.state, source);

        // Create new state object
        const previousState = { ...this.state };
        const newState = {
            ...this.state,
            ...updates,
            updatedAt: new Date().toISOString()
        };

        // Validate state changes
        if (!this.validateStateUpdate(previousState, newState)) {
            console.error('[StateManager] Invalid state update rejected:', updates);
            return;
        }

        this.state = newState;

        if (this.debugMode) {
            console.log(`[StateManager] State updated by '${source}':`, {
                updates,
                previousState: previousState,
                newState: this.state
            });
        }

        // Emit state change events
        this.emitStateChanges(previousState, newState, source);
    }

    /**
     * Validate state updates
     * @param {Object} previousState - Previous state
     * @param {Object} newState - New state
     * @returns {boolean} Whether the update is valid
     */
    validateStateUpdate(previousState, newState) {
        // Validate status transitions
        const validStatusTransitions = {
            'idle': ['planning', 'error'],
            'planning': ['awaiting_approval', 'executing', 'error', 'idle'],
            'awaiting_approval': ['planning', 'executing', 'error'],
            'executing': ['completed', 'error', 'awaiting_approval'],
            'completed': ['idle'],
            'error': ['idle', 'planning']
        };

        if (newState.status !== previousState.status) {
            const validTransitions = validStatusTransitions[previousState.status] || [];
            if (!validTransitions.includes(newState.status)) {
                console.warn(`[StateManager] Invalid status transition: ${previousState.status} -> ${newState.status}`);
                // Allow transition but log warning
            }
        }

        // Validate required fields for certain states (only in production-like scenarios)
        if (newState.status === 'executing' && !newState.plan && !newState.threadId) {
            console.warn('[StateManager] Transitioning to executing without plan or threadId');
            // Allow transition but warn - useful for testing and edge cases
        }

        if (newState.status === 'completed' && !newState.finalReport) {
            console.warn('[StateManager] Completing without final report');
        }

        return true;
    }

    /**
     * Add state to history
     * @param {Object} state - State to add to history
     * @param {string} source - Source of the change
     */
    addToHistory(state, source) {
        this.history.push({
            state: JSON.parse(JSON.stringify(state)),
            timestamp: new Date().toISOString(),
            source
        });

        // Limit history size
        if (this.history.length > this.maxHistorySize) {
            this.history.shift();
        }
    }

    /**
     * Emit state change events
     * @param {Object} previousState - Previous state
     * @param {Object} newState - New state
     * @param {string} source - Source of the change
     */
    emitStateChanges(previousState, newState, source) {
        // Emit general state change event
        this.eventBus.emit('stateChanged', {
            previousState,
            newState,
            source,
            timestamp: new Date().toISOString()
        });

        // Emit specific change events
        Object.keys(newState).forEach(key => {
            if (previousState[key] !== newState[key]) {
                this.eventBus.emit(`state:${key}Changed`, {
                    key,
                    previousValue: previousState[key],
                    newValue: newState[key],
                    source
                });
            }
        });

        // Emit status-specific events
        if (previousState.status !== newState.status) {
            this.eventBus.emit('statusChanged', {
                from: previousState.status,
                to: newState.status,
                source
            });

            this.eventBus.emit(`status:${newState.status}`, {
                state: newState,
                source
            });
        }
    }

    /**
     * Subscribe to state changes
     * @param {Function} callback - Callback function
     * @returns {Function} Unsubscribe function
     */
    subscribe(callback) {
        return this.eventBus.on('stateChanged', callback);
    }

    /**
     * Subscribe to specific state property changes
     * @param {string} property - Property name to watch
     * @param {Function} callback - Callback function
     * @returns {Function} Unsubscribe function
     */
    subscribeToProperty(property, callback) {
        return this.eventBus.on(`state:${property}Changed`, callback);
    }

    /**
     * Subscribe to status changes
     * @param {Function} callback - Callback function
     * @returns {Function} Unsubscribe function
     */
    subscribeToStatus(callback) {
        return this.eventBus.on('statusChanged', callback);
    }

    /**
     * Subscribe to specific status
     * @param {string} status - Status to watch for
     * @param {Function} callback - Callback function
     * @returns {Function} Unsubscribe function
     */
    subscribeToStatusChange(status, callback) {
        return this.eventBus.on(`status:${status}`, callback);
    }

    /**
     * Reset state to initial values
     */
    reset() {
        const initialState = this.getInitialState();
        this.setState(initialState, 'reset');
        this.history = [];

        if (this.debugMode) {
            console.log('[StateManager] State reset to initial values');
        }
    }

    /**
     * Get state history
     * @returns {Array} State history
     */
    getHistory() {
        return [...this.history];
    }

    /**
     * Rollback to previous state
     * @param {number} steps - Number of steps to rollback (default: 1)
     */
    rollback(steps = 1) {
        if (this.history.length < steps) {
            console.warn(`[StateManager] Cannot rollback ${steps} steps, only ${this.history.length} available`);
            return;
        }

        const targetHistoryEntry = this.history[this.history.length - steps];
        this.state = JSON.parse(JSON.stringify(targetHistoryEntry.state));

        // Remove rolled back entries from history
        this.history = this.history.slice(0, -steps);

        if (this.debugMode) {
            console.log(`[StateManager] Rolled back ${steps} steps to:`, targetHistoryEntry);
        }

        // Emit rollback event
        this.eventBus.emit('stateRolledBack', {
            steps,
            newState: this.state,
            timestamp: new Date().toISOString()
        });
    }

    /**
     * Enable/disable debug mode
     * @param {boolean} enabled - Whether to enable debug mode
     */
    setDebugMode(enabled) {
        this.debugMode = enabled;
        this.setState({
            preferences: {
                ...this.state.preferences,
                debugMode: enabled
            }
        }, 'debugMode');
    }

    /**
     * Get state statistics
     * @returns {Object} State statistics
     */
    getStats() {
        return {
            historySize: this.history.length,
            stateSize: JSON.stringify(this.state).length,
            uptime: Date.now() - new Date(this.state.createdAt).getTime(),
            lastUpdated: this.state.updatedAt,
            eventListeners: this.eventBus.getEventNames().reduce((acc, eventName) => {
                acc[eventName] = this.eventBus.getListenerCount(eventName);
                return acc;
            }, {})
        };
    }
}

// Create singleton instances
export const eventBus = new EventBus();
export const stateManager = new StateManager(eventBus);

// Export for testing and debugging
if (typeof window !== 'undefined') {
    window.clarityState = {
        eventBus,
        stateManager,
        enableDebug: () => {
            eventBus.setDebugMode(true);
            stateManager.setDebugMode(true);
        },
        disableDebug: () => {
            eventBus.setDebugMode(false);
            stateManager.setDebugMode(false);
        }
    };
}