/**
 * Main JavaScript file for Portfolio Manager
 */

document.addEventListener('DOMContentLoaded', () => {
    // Initialize UI components
    initializeModals();
    initializeDropdowns();
    initializeNotifications();
    initializeTabs();
    
    // Setup AJAX error handling
    setupAjaxErrorHandling();
});

/**
 * Initialize modal functionality
 */
function initializeModals() {
    // Functions to open and close modals
    function openModal($el) {
        $el.classList.add('is-active');
        document.documentElement.classList.add('is-clipped');
    }

    function closeModal($el) {
        $el.classList.remove('is-active');
        document.documentElement.classList.remove('is-clipped');
    }

    function closeAllModals() {
        (document.querySelectorAll('.modal') || []).forEach(($modal) => {
            closeModal($modal);
        });
    }

    // Add click events to modal triggers
    (document.querySelectorAll('.js-modal-trigger') || []).forEach(($trigger) => {
        const modal = $trigger.dataset.target;
        const $target = document.getElementById(modal);

        $trigger.addEventListener('click', () => {
            openModal($target);
        });
    });

    // Add click events to close buttons
    (document.querySelectorAll('.modal-background, .modal-close, .modal-card-head .delete, .modal-card-foot .button.modal-cancel') || []).forEach(($close) => {
        const $target = $close.closest('.modal');

        $close.addEventListener('click', () => {
            closeModal($target);
        });
    });

    // Close modals with Escape key
    document.addEventListener('keydown', (event) => {
        if(event.key === "Escape") {
            closeAllModals();
        }
    });
}

/**
 * Initialize dropdown functionality
 */
function initializeDropdowns() {
    // Get all dropdowns on the page
    const dropdowns = document.querySelectorAll('.dropdown:not(.is-hoverable)');

    if (dropdowns.length > 0) {
        // For each dropdown, add event listener to toggle button
        dropdowns.forEach(dropdown => {
            const trigger = dropdown.querySelector('.dropdown-trigger');
            const menu = dropdown.querySelector('.dropdown-menu');
            
            if (trigger && menu) {
                trigger.addEventListener('click', function(event) {
                    event.stopPropagation();
                    dropdown.classList.toggle('is-active');
                });
                
                // Close dropdown when clicking outside
                document.addEventListener('click', function() {
                    dropdown.classList.remove('is-active');
                });
                
                // Prevent menu clicks from closing dropdown
                menu.addEventListener('click', function(event) {
                    event.stopPropagation();
                });
            }
        });
    }
}

/**
 * Initialize notification handling
 */
function initializeNotifications() {
    // Get all notifications with a delete button
    const notifications = document.querySelectorAll('.notification:not(.is-permanent) .delete');
    
    // Add click event to each delete button
    notifications.forEach(deleteButton => {
        const notification = deleteButton.parentNode;
        
        // Add event listener for deletion
        deleteButton.addEventListener('click', () => {
            notification.parentNode.removeChild(notification);
        });
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            if (notification && notification.parentNode) {
                notification.classList.add('is-fading-out');
                setTimeout(() => {
                    if (notification && notification.parentNode) {
                        notification.parentNode.removeChild(notification);
                    }
                }, 500);
            }
        }, 5000);
    });
}

/**
 * Initialize tabs functionality
 */
function initializeTabs() {
    const tabGroups = document.querySelectorAll('.tabs');
    
    tabGroups.forEach(tabGroup => {
        const tabs = tabGroup.querySelectorAll('li');
        const tabContents = document.querySelectorAll('.tab-content');
        
        tabs.forEach(tab => {
            const target = tab.dataset.target;
            
            tab.addEventListener('click', () => {
                // Deactivate all tabs
                tabs.forEach(t => t.classList.remove('is-active'));
                
                // Hide all tab contents
                tabContents.forEach(content => content.classList.add('is-hidden'));
                
                // Activate clicked tab
                tab.classList.add('is-active');
                
                // Show corresponding content
                if (target) {
                    const targetContent = document.getElementById(target);
                    if (targetContent) {
                        targetContent.classList.remove('is-hidden');
                    }
                }
            });
        });
    });
}

/**
 * Setup AJAX error handling
 */
function setupAjaxErrorHandling() {
    // Add global error handling for Axios
    if (window.axios) {
        axios.interceptors.response.use(
            response => response,
            error => {
                console.error('AJAX Error:', error);
                
                let errorMessage = 'An unexpected error occurred';
                
                if (error.response) {
                    // The server responded with an error status
                    if (error.response.data && error.response.data.error) {
                        errorMessage = error.response.data.error;
                    } else {
                        errorMessage = `Server error: ${error.response.status}`;
                    }
                } else if (error.request) {
                    // The request was made but no response was received
                    errorMessage = 'No response from server. Please check your connection.';
                }
                
                // Create and show error notification
                showNotification(errorMessage, 'is-danger');
                
                return Promise.reject(error);
            }
        );
    }
}

/**
 * Show notification
 * @param {string} message - Message to display
 * @param {string} type - Notification type (is-info, is-success, is-warning, is-danger)
 * @param {number} duration - Duration in milliseconds (0 for permanent)
 */
function showNotification(message, type = 'is-info', duration = 5000) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    
    // Add delete button
    const deleteButton = document.createElement('button');
    deleteButton.className = 'delete';
    notification.appendChild(deleteButton);
    
    // Add message text
    const messageText = document.createTextNode(message);
    notification.appendChild(messageText);
    
    // Add notification to container
    const container = document.querySelector('.container') || document.body;
    container.insertBefore(notification, container.firstChild);
    
    // Setup delete button
    deleteButton.addEventListener('click', () => {
        notification.remove();
    });
    
    // Auto-dismiss if duration > 0
    if (duration > 0) {
        setTimeout(() => {
            notification.classList.add('is-fading-out');
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, 500);
        }, duration);
    }
}

/**
 * Format currency with symbol
 * @param {number} amount - Amount to format
 * @param {string} currency - Currency symbol
 * @returns {string} Formatted currency string
 */
function formatCurrency(amount, currency = '€') {
    if (typeof amount !== 'number') {
        return `${currency}0`;
    }
    
    return amount >= 100
        ? `${currency}${amount.toLocaleString('en-US', {maximumFractionDigits: 0})}`
        : `${currency}${amount.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
}

/**
 * Format percentage
 * @param {number} value - Value to format as percentage
 * @param {number} decimals - Number of decimal places
 * @param {boolean} includeSymbol - Whether to include % symbol
 * @returns {string} Formatted percentage
 */
function formatPercentage(value, decimals = 1, includeSymbol = true) {
    if (typeof value !== 'number') {
        return includeSymbol ? '0%' : '0';
    }
    
    const formatted = value.toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
    
    return includeSymbol ? `${formatted}%` : formatted;
}

/**
 * Create loading overlay
 * @returns {Object} Loading overlay control object
 */
function createLoadingOverlay() {
    // Create elements
    const overlay = document.createElement('div');
    overlay.className = 'loading-overlay';
    
    const spinner = document.createElement('div');
    spinner.className = 'spinner';
    overlay.appendChild(spinner);
    
    // Return control object
    return {
        show: function() {
            document.body.appendChild(overlay);
            document.body.style.overflow = 'hidden';
        },
        hide: function() {
            if (overlay.parentNode) {
                overlay.parentNode.removeChild(overlay);
                document.body.style.overflow = '';
            }
        }
    };
}

/**
 * Debounce function to limit function call frequency
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds
 * @returns {Function} Debounced function
 */
function debounce(func, wait = 300) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

// Export global utilities
window.portfolioManager = {
    formatCurrency,
    formatPercentage,
    showNotification,
    createLoadingOverlay,
    debounce
};