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

        async savePortfolioChange(item) {
            console.log('savePortfolioChange called with item:', item);
            if (!item || !item.id) {
                console.error('Invalid item for portfolio change');
                return;
            }
            
            try {
                console.log('Sending portfolio update request for item ID:', item.id, 'Portfolio:', item.portfolio);
                const response = await fetch(`/portfolio/api/update_portfolio/${item.id}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        portfolio: item.portfolio || ''
                    })
                });
                
                const result = await response.json();
                console.log('Portfolio update response:', result);
                
                if (result.success) {
                    // Show success notification using the global function if available
                    if (typeof showNotification === 'function') {
                        showNotification('Portfolio updated successfully', 'is-success', 3000);
                    } else {
                        console.log('Portfolio updated successfully');
                    }
                } else {
                    // Show error notification
                    if (typeof showNotification === 'function') {
                        showNotification(`Error updating portfolio: ${result.error}`, 'is-danger');
                    } else {
                        console.error(`Error updating portfolio: ${result.error}`);
                    }
                }
            } catch (error) {
                console.error('Error updating portfolio:', error);
                if (typeof showNotification === 'function') {
                    showNotification('Failed to update portfolio', 'is-danger');
                }
            }
        },
        
        debouncedSavePortfolioChange: _.debounce(function(item) {
            this.savePortfolioChange(item);
        }, 500),
        
        // Save identifier changes to the database
        async saveIdentifierChange(item) {
            if (!item || !item.id) {
                console.error('Invalid item for identifier change');
                return;
            }
            
            try {
                const response = await fetch(`/portfolio/api/update_portfolio/${item.id}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        identifier: item.identifier || ''
                    })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    // Show success notification using the global function if available
                    if (typeof showNotification === 'function') {
                        showNotification('Identifier updated successfully', 'is-success', 3000);
                    } else {
                        console.log('Identifier updated successfully');
                    }
                } else {
                    // Show error notification
                    if (typeof showNotification === 'function') {
                        showNotification(`Error updating identifier: ${result.error}`, 'is-danger');
                    } else {
                        console.error(`Error updating identifier: ${result.error}`);
                    }
                }
            } catch (error) {
                console.error('Error updating identifier:', error);
                if (typeof showNotification === 'function') {
                    showNotification('Failed to update identifier', 'is-danger');
                }
            }
        },
        
        // Debounced version of saveIdentifierChange for input events
        debouncedSaveIdentifierChange: _.debounce(function(item) {
            this.saveIdentifierChange(item);
        }, 500),

        async saveCategoryChange(item) {
            console.log('saveCategoryChange called with item:', item);
            if (!item || !item.id) {
                console.error('Invalid item for category change');
                return;
            }
            
            try {
                console.log('Sending category update request for item ID:', item.id, 'Category:', item.category);
                const response = await fetch(`/portfolio/api/update_portfolio/${item.id}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        category: item.category || ''
                    })
                });
                
                const result = await response.json();
                console.log('Category update response:', result);
                
                if (result.success) {
                    // Show success notification using the global function if available
                    if (typeof showNotification === 'function') {
                        showNotification('Category updated successfully', 'is-success', 3000);
                    } else {
                        console.log('Category updated successfully');
                    }
                } else {
                    // Show error notification
                    if (typeof showNotification === 'function') {
                        showNotification(`Error updating category: ${result.error}`, 'is-danger');
                    } else {
                        console.error(`Error updating category: ${result.error}`);
                    }
                }
            } catch (error) {
                console.error('Error updating category:', error);
                if (typeof showNotification === 'function') {
                    showNotification('Failed to update category', 'is-danger');
                }
            }
        },
        
        // Debounced version of saveCategoryChange for input events
        debouncedSaveCategoryChange: _.debounce(function(item) {
            this.saveCategoryChange(item);
        }, 500),

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
        console.log('Vue component mounted. Methods available:', Object.keys(this.$options.methods).join(', '));
        this.loadData();
    }
});