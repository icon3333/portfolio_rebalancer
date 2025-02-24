// Portfolio Table Vue Application
const app = new Vue({
    el: '#portfolio-table-app',
    data() {
        return {
            portfolioItems: [],
            portfolioOptions: [],
            selectedItem: {},
            showUpdatePriceModal: false,
            showDeleteModal: false,
            isUpdating: false,
            isUpdatingAll: false,
            isUpdatingMissing: false,
            isDeleting: false,
            loading: false,
            metrics: {
                total: 0,
                health: 0,
                missing: 0,
                totalValue: 0,
                lastUpdate: null
            }
        };
    },
    computed: {
        healthColorClass() {
            if (!this.portfolioItems.length) return 'is-info';
            const health = this.metrics.health;
            if (health >= 90) return 'is-success';
            if (health >= 70) return 'is-warning';
            return 'is-danger';
        }
    },
    methods: {
        async loadData() {
            this.loading = true;
            try {
                const response = await fetch('/portfolio/api/portfolio_data');
                const data = await response.json();
                this.portfolioItems = data;
                this.updateMetrics();
            } catch (error) {
                console.error('Error loading portfolio data:', error);
            } finally {
                this.loading = false;
            }
        },
        
        updateMetrics() {
            const items = this.portfolioItems;
            this.metrics = {
                total: items.length,
                health: items.length ? Math.round(((items.length - items.filter(i => !i.price_eur).length) / items.length) * 100) : 100,
                missing: items.filter(i => !i.price_eur).length,
                totalValue: items.reduce((sum, item) => sum + ((item.price_eur || 0) * (item.shares || 0)), 0),
                lastUpdate: items.reduce((latest, item) => !latest || (item.last_updated && item.last_updated > latest) ? item.last_updated : latest, null)
            };
        },

        async updateAllPrices() {
            this.isUpdatingAll = true;
            try {
                // Show loading notification
                const loadingNotification = document.createElement('div');
                loadingNotification.className = 'notification is-info is-light';
                loadingNotification.innerHTML = `
                    <button class="delete"></button>
                    <div>
                        <p class="mb-2">Updating all prices...</p>
                        <progress class="progress is-info" value="0" max="100">0%</progress>
                    </div>
                `;
                
                // Add notification to page
                const container = document.querySelector('.columns');
                container.insertBefore(loadingNotification, container.firstChild);
                
                // Start progress updates
                const progressBar = loadingNotification.querySelector('progress');
                const eventSource = new EventSource('/portfolio/api/update_progress');
                eventSource.onmessage = (event) => {
                    const progress = parseInt(event.data);
                    progressBar.value = progress;
                    if (progress >= 100) {
                        eventSource.close();
                    }
                };
                
                const response = await fetch('/portfolio/api/update_all_prices', {
                    method: 'POST'
                });
                const result = await response.json();
                
                // Remove loading notification
                eventSource.close();
                if (loadingNotification.parentNode) {
                    loadingNotification.remove();
                }
                
                if (response.ok) {
                    const updatedCount = Object.keys(result.updated).length;
                    const failedCount = result.failed.length;
                    
                    let message = `Updated ${updatedCount} prices successfully.`;
                    if (failedCount > 0) {
                        message += ` Failed to update ${failedCount} prices.`;
                    }
                    
                    // Show success notification
                    const notification = document.createElement('div');
                    notification.className = `notification is-${failedCount === 0 ? 'success' : 'warning'} is-light`;
                    notification.innerHTML = `
                        <button class="delete"></button>
                        ${message}
                    `;
                    
                    // Add notification to page
                    container.insertBefore(notification, container.firstChild);
                    
                    // Add click handler to delete button
                    notification.querySelector('.delete').addEventListener('click', () => {
                        notification.remove();
                    });
                    
                    // Auto-remove after 5 seconds
                    setTimeout(() => {
                        if (notification.parentNode) {
                            notification.remove();
                        }
                    }, 5000);
                    
                    // Refresh data
                    await this.loadData();
                }
            } catch (error) {
                console.error('Error updating all prices:', error);
            } finally {
                this.isUpdatingAll = false;
            }
        },
        
        async updateMissingPrices() {
            this.isUpdatingMissing = true;
            try {
                // Get items with missing prices
                const missingItems = this.portfolioItems.filter(item => !item.price_eur);
                if (missingItems.length === 0) {
                    // Show info notification
                    const notification = document.createElement('div');
                    notification.className = 'notification is-info is-light';
                    notification.innerHTML = `
                        <button class="delete"></button>
                        No missing prices to update.
                    `;
                    
                    // Add notification to page
                    const container = document.querySelector('.columns');
                    container.insertBefore(notification, container.firstChild);
                    
                    // Add click handler to delete button
                    notification.querySelector('.delete').addEventListener('click', () => {
                        notification.remove();
                    });
                    
                    // Auto-remove after 5 seconds
                    setTimeout(() => {
                        if (notification.parentNode) {
                            notification.remove();
                        }
                    }, 5000);
                    return;
                }
                
                // Show loading notification
                const loadingNotification = document.createElement('div');
                loadingNotification.className = 'notification is-info is-light';
                loadingNotification.innerHTML = `
                    <button class="delete"></button>
                    <div>
                        <p class="mb-2">Updating missing prices...</p>
                        <progress class="progress is-info" value="0" max="100">0%</progress>
                    </div>
                `;
                
                // Add notification to page
                const container = document.querySelector('.columns');
                container.insertBefore(loadingNotification, container.firstChild);
                
                // Start progress updates
                const progressBar = loadingNotification.querySelector('progress');
                const eventSource = new EventSource('/portfolio/api/update_progress');
                eventSource.onmessage = (event) => {
                    const progress = parseInt(event.data);
                    progressBar.value = progress;
                    if (progress >= 100) {
                        eventSource.close();
                    }
                };
                
                // Update missing prices
                const response = await fetch('/portfolio/api/update_all_prices', {
                    method: 'POST'
                });
                const result = await response.json();
                
                // Remove loading notification
                eventSource.close();
                if (loadingNotification.parentNode) {
                    loadingNotification.remove();
                }
                
                if (response.ok) {
                    const updatedCount = Object.keys(result.updated).length;
                    const failedCount = result.failed.length;
                    
                    let message = `Updated ${updatedCount} missing prices successfully.`;
                    if (failedCount > 0) {
                        message += ` Failed to update ${failedCount} prices.`;
                    }
                    
                    // Show success notification
                    const notification = document.createElement('div');
                    notification.className = `notification is-${failedCount === 0 ? 'success' : 'warning'} is-light`;
                    notification.innerHTML = `
                        <button class="delete"></button>
                        ${message}
                    `;
                    
                    // Add notification to page
                    container.insertBefore(notification, container.firstChild);
                    
                    // Add click handler to delete button
                    notification.querySelector('.delete').addEventListener('click', () => {
                        notification.remove();
                    });
                    
                    // Auto-remove after 5 seconds
                    setTimeout(() => {
                        if (notification.parentNode) {
                            notification.remove();
                        }
                    }, 5000);
                    
                    // Refresh data
                    await this.loadData();
                }
            } catch (error) {
                console.error('Error updating missing prices:', error);
            } finally {
                this.isUpdatingMissing = false;
            }
        },

        formatCurrency(value) {
            if (!value) return '€0.00';
            return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(value);
        },

        formatNumber(value) {
            if (!value) return '0';
            return new Intl.NumberFormat('de-DE').format(value);
        },

        formatDateAgo(date) {
            if (!date) return 'Never';
            const d = new Date(date);
            const now = new Date();
            const diff = Math.floor((now - d) / 1000); // seconds

            if (diff < 60) return 'Just now';
            if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
            if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
            if (diff < 2592000) return `${Math.floor(diff / 86400)}d ago`;
            return d.toLocaleDateString();
        }
    },
    mounted() {
        this.loadData();
    }
});