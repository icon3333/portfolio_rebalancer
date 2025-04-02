document.addEventListener('DOMContentLoaded', function() {
    // Get tab elements
    const globalTab = document.getElementById('global-tab');
    const detailedTab = document.getElementById('detailed-tab');
    const globalContent = document.getElementById('global');
    const detailedContent = document.getElementById('detailed');

    // Function to handle tab switching
    function switchTab(tabId) {
        // Remove active class from all tabs and content
        [globalTab, detailedTab].forEach(tab => tab.classList.remove('active'));
        [globalContent, detailedContent].forEach(content => {
            content.classList.remove('active');
            content.style.display = 'none';
        });

        // Add active class to selected tab and content
        if (tabId === 'global') {
            globalTab.classList.add('active');
            globalContent.classList.add('active');
            globalContent.style.display = 'block';
        } else {
            detailedTab.classList.add('active');
            detailedContent.classList.add('active');
            detailedContent.style.display = 'block';
        }

        // Add smooth transition effect
        const activeContent = tabId === 'global' ? globalContent : detailedContent;
        activeContent.style.transition = 'opacity 0.3s ease-in-out';
        activeContent.style.opacity = '0';
        
        setTimeout(() => {
            activeContent.style.opacity = '1';
        }, 50);
    }

    // Add click event listeners to tabs
    globalTab.addEventListener('click', () => switchTab('global'));
    detailedTab.addEventListener('click', () => switchTab('detailed'));

    // Add hover effect to tabs
    [globalTab, detailedTab].forEach(tab => {
        tab.addEventListener('mouseenter', () => {
            if (!tab.classList.contains('active')) {
                tab.style.backgroundColor = '#f8f9fa';
            }
        });
        
        tab.addEventListener('mouseleave', () => {
            if (!tab.classList.contains('active')) {
                tab.style.backgroundColor = '';
            }
        });
    });
});
