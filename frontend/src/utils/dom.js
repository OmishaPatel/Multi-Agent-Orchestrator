/**
 * DOM Utilities
 * 
 * Provides utility functions for efficient DOM manipulation
 * Used by components for creating, updating, and managing DOM elements
 */

export class DOMUtils {
    /**
     * Create a new DOM element with optional class and text content
     */
    static createElement(tag, className = '', textContent = '') {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (textContent) element.textContent = textContent;
        return element;
    }

    /**
     * Clear all child elements from a parent element
     */
    static clearElement(element) {
        while (element.firstChild) {
            element.removeChild(element.firstChild);
        }
    }

    /**
     * Show an element by removing display: none
     */
    static show(element) {
        if (element) {
            element.style.display = '';
        }
    }

    /**
     * Hide an element by setting display: none
     */
    static hide(element) {
        if (element) {
            element.style.display = 'none';
        }
    }

    /**
     * Add a CSS class to an element
     */
    static addClass(element, className) {
        if (element && className) {
            element.classList.add(className);
        }
    }

    /**
     * Remove a CSS class from an element
     */
    static removeClass(element, className) {
        if (element && className) {
            element.classList.remove(className);
        }
    }

    /**
     * Toggle a CSS class on an element
     */
    static toggleClass(element, className) {
        if (element && className) {
            element.classList.toggle(className);
        }
    }

    /**
     * Check if an element has a specific class
     */
    static hasClass(element, className) {
        return element && className && element.classList.contains(className);
    }

    /**
     * Set multiple attributes on an element
     */
    static setAttributes(element, attributes) {
        if (element && attributes) {
            Object.entries(attributes).forEach(([key, value]) => {
                element.setAttribute(key, value);
            });
        }
    }

    /**
     * Create element with attributes and content
     */
    static createElementWithAttributes(tag, attributes = {}, textContent = '') {
        const element = document.createElement(tag);
        this.setAttributes(element, attributes);
        if (textContent) element.textContent = textContent;
        return element;
    }

    /**
     * Efficiently update text content if it has changed
     */
    static updateTextContent(element, newText) {
        if (element && element.textContent !== newText) {
            element.textContent = newText;
        }
    }

    /**
     * Efficiently update innerHTML if it has changed
     */
    static updateInnerHTML(element, newHTML) {
        if (element && element.innerHTML !== newHTML) {
            element.innerHTML = newHTML;
        }
    }

    /**
     * Add event listener with automatic cleanup tracking
     */
    static addEventListener(element, event, handler, options = {}) {
        if (element && event && handler) {
            element.addEventListener(event, handler, options);

            // Return cleanup function
            return () => element.removeEventListener(event, handler, options);
        }
        return () => { };
    }

    /**
     * Debounce function for performance optimization
     */
    static debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    /**
     * Throttle function for performance optimization
     */
    static throttle(func, limit) {
        let inThrottle;
        return function executedFunction(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }

    /**
     * Check if element is visible in viewport
     */
    static isInViewport(element) {
        if (!element) return false;

        const rect = element.getBoundingClientRect();
        return (
            rect.top >= 0 &&
            rect.left >= 0 &&
            rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
            rect.right <= (window.innerWidth || document.documentElement.clientWidth)
        );
    }

    /**
     * Smooth scroll to element
     */
    static scrollToElement(element, options = {}) {
        if (element) {
            element.scrollIntoView({
                behavior: 'smooth',
                block: 'start',
                inline: 'nearest',
                ...options
            });
        }
    }

    /**
     * Get element's computed style property
     */
    static getComputedStyle(element, property) {
        if (element && property) {
            return window.getComputedStyle(element).getPropertyValue(property);
        }
        return null;
    }

    /**
     * Set CSS custom property (CSS variable)
     */
    static setCSSProperty(element, property, value) {
        if (element && property && value !== undefined) {
            element.style.setProperty(property, value);
        }
    }

    /**
     * Get CSS custom property value
     */
    static getCSSProperty(element, property) {
        if (element && property) {
            return element.style.getPropertyValue(property);
        }
        return null;
    }

    /**
     * Create a document fragment for efficient DOM manipulation
     */
    static createFragment() {
        return document.createDocumentFragment();
    }

    /**
     * Append multiple children to a parent element efficiently
     */
    static appendChildren(parent, children) {
        if (parent && children) {
            const fragment = this.createFragment();
            children.forEach(child => {
                if (child) fragment.appendChild(child);
            });
            parent.appendChild(fragment);
        }
    }

    /**
     * Find closest parent element matching selector
     */
    static closest(element, selector) {
        if (element && selector) {
            return element.closest(selector);
        }
        return null;
    }

    /**
     * Query selector with error handling
     */
    static querySelector(selector, parent = document) {
        try {
            return parent.querySelector(selector);
        } catch (error) {
            console.warn('Invalid selector:', selector, error);
            return null;
        }
    }

    /**
     * Query all elements with error handling
     */
    static querySelectorAll(selector, parent = document) {
        try {
            return Array.from(parent.querySelectorAll(selector));
        } catch (error) {
            console.warn('Invalid selector:', selector, error);
            return [];
        }
    }

    /**
     * Wait for element to appear in DOM
     */
    static waitForElement(selector, timeout = 5000) {
        return new Promise((resolve, reject) => {
            const element = this.querySelector(selector);
            if (element) {
                resolve(element);
                return;
            }

            const observer = new MutationObserver((mutations, obs) => {
                const element = this.querySelector(selector);
                if (element) {
                    obs.disconnect();
                    resolve(element);
                }
            });

            observer.observe(document.body, {
                childList: true,
                subtree: true
            });

            setTimeout(() => {
                observer.disconnect();
                reject(new Error(`Element ${selector} not found within ${timeout}ms`));
            }, timeout);
        });
    }

    /**
     * Copy text to clipboard
     */
    static async copyToClipboard(text) {
        try {
            if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(text);
                return true;
            } else {
                // Fallback for older browsers
                const textArea = document.createElement('textarea');
                textArea.value = text;
                textArea.style.position = 'fixed';
                textArea.style.left = '-999999px';
                textArea.style.top = '-999999px';
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();

                const success = document.execCommand('copy');
                textArea.remove();
                return success;
            }
        } catch (error) {
            console.error('Failed to copy text:', error);
            return false;
        }
    }

    /**
     * Format file size for display
     */
    static formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';

        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));

        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    /**
     * Escape HTML to prevent XSS
     */
    static escapeHTML(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Create a safe HTML string from template
     */
    static createSafeHTML(template, data = {}) {
        let html = template;

        Object.entries(data).forEach(([key, value]) => {
            const placeholder = new RegExp(`{{${key}}}`, 'g');
            html = html.replace(placeholder, this.escapeHTML(String(value)));
        });

        return html;
    }
}