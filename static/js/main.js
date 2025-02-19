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