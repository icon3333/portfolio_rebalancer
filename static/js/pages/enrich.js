/**
 * Portfolio Enrichment Page JavaScript
 * Handles file uploads, portfolio management, and data visualization
 */

// DOM Elements and Utility Functions
const FileUploadHandler = {
    init() {
        const fileInput = document.querySelector('.file-input');
        const fileLabel = document.querySelector('.file-name');
        const progressElement = document.getElementById('price-fetch-progress');
        const progressCount = document.getElementById('progress-count');
        const progressTotal = document.getElementById('progress-total');
        const progressPercentage = document.getElementById('progress-percentage');
        const uploadForm = document.querySelector('form[action*="upload"]');
        
        if (!fileInput || !fileLabel) {
            console.error('Required file upload elements not found');
            return;
        }

        // Initialize progress display
        progressCount.textContent = '0';
        progressTotal.textContent = '0';
        progressPercentage.textContent = '0%';
        progressElement.style.display = 'none';
        
        // File selection handler
        fileInput.addEventListener('change', function() {
            if (fileInput.files.length > 0) {
                fileLabel.textContent = fileInput.files[0].name;
                
                // Show the progress indicator immediately
                progressCount.textContent = '0';
                progressTotal.textContent = '0';
                progressPercentage.textContent = '0%';
                progressElement.style.display = 'block';
                progressElement.dataset.processing = 'true';
                
                // Start progress tracking
                if (PriceProgressTracker.progressInterval) {
                    clearInterval(PriceProgressTracker.progressInterval);
                }
                
                PriceProgressTracker.progressInterval = setInterval(() => {
                    PriceProgressTracker.checkProgress(
                        progressElement,
                        progressCount,
                        progressTotal,
                        progressPercentage
                    );
                }, 500);
                
                // Run once immediately
                PriceProgressTracker.checkProgress(
                    progressElement,
                    progressCount,
                    progressTotal,
                    progressPercentage
                );
                
                // Automatically submit the form
                if (uploadForm) {
                    uploadForm.submit();
                }
            } else {
                fileLabel.textContent = 'No file selected';
            }
        });
        
        // Form submission handler
        if (uploadForm) {
            uploadForm.addEventListener('submit', function() {
                console.log("Form submitted, starting progress tracking");
                
                // Reset progress indicators
                progressCount.textContent = '0';
                progressTotal.textContent = '0';
                progressPercentage.textContent = '0%';
                
                // Show the progress indicator immediately when the form is submitted
                progressElement.style.display = 'block';
                progressElement.dataset.processing = 'true';
                
                // Clear any existing interval and start a new one - use PriceProgressTracker consistently
                if (PriceProgressTracker.progressInterval) {
                    clearInterval(PriceProgressTracker.progressInterval);
                }
                
                // Create a new interval with more frequent updates during processing
                PriceProgressTracker.progressInterval = setInterval(() => {
                    PriceProgressTracker.checkProgress(
                        progressElement,
                        progressCount,
                        progressTotal,
                        progressPercentage
                    );
                }, 500);
                
                // Also run once immediately
                PriceProgressTracker.checkProgress(
                    progressElement,
                    progressCount,
                    progressTotal,
                    progressPercentage
                );
            });
        }
    }
};

const PriceProgressTracker = {
    progressInterval: null,
    
    checkProgress(progressElement, progressCount, progressTotal, progressPercentage) {
        fetch('/portfolio/api/price_fetch_progress')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log("Progress data:", data);
                
                // Update the progress display
                progressCount.textContent = data.current || 0;
                progressTotal.textContent = data.total || 0;
                
                // Use percentage directly from the server
                const percentage = data.percentage || 0;
                progressPercentage.textContent = percentage + '%';
                
                // Update progress bar
                const progressBar = document.getElementById('progress-bar');
                if (progressBar) {
                    // Update the value attribute instead of the width style
                    progressBar.value = percentage;
                }
                
                // Only show the progress indicator if there's actual progress happening
                // or if we're in processing mode (set by form submission)
                if (data.total > 0 || progressElement.dataset.processing === 'true') {
                    progressElement.style.display = 'block';
                    
                    // If we're done, hide after a delay
                    if (data.current >= data.total && data.total > 0) {
                        console.log("Process complete, hiding indicator soon");
                        clearInterval(this.progressInterval);
                        setTimeout(() => {
                            progressElement.style.display = 'none';
                            // Clear processing flag
                            delete progressElement.dataset.processing;
                        }, 3000);
                    }
                } else {
                    // Check if we should keep showing while processing
                    if (!progressElement.dataset.processing) {
                        progressElement.style.display = 'none';
                    }
                }
            })
            .catch(error => {
                console.error('Error checking price fetch progress:', error);
            });
    }
};

const PortfolioManager = {
    init() {
        const actionSelect = document.getElementById('portfolio-action');
        const actionButton = document.getElementById('portfolio-action-btn');
        const addFields = document.getElementById('add-portfolio-fields');
        const renameFields = document.getElementById('rename-portfolio-fields');
        const deleteFields = document.getElementById('delete-portfolio-fields');
        const portfolioForm = document.getElementById('manage-portfolios-form');
        
        if (!actionSelect || !actionButton) {
            console.error('Required portfolio management elements not found');
            return;
        }
        
        // Action selection handler
        actionSelect.addEventListener('change', function() {
            const action = this.value;
            
            // Hide all fields first
            addFields.classList.add('is-hidden');
            renameFields.classList.add('is-hidden');
            deleteFields.classList.add('is-hidden');
            
            // Enable/disable action button
            actionButton.disabled = !action;
            
            // Show relevant fields based on action
            if (action === 'add') {
                addFields.classList.remove('is-hidden');
            } else if (action === 'rename') {
                renameFields.classList.remove('is-hidden');
            } else if (action === 'delete') {
                deleteFields.classList.remove('is-hidden');
            }
        });
        
        // Form validation before submit
        if (portfolioForm) {
            portfolioForm.addEventListener('submit', function(e) {
                const action = actionSelect.value;
                
                if (action === 'add') {
                    const addNameField = document.querySelector('input[name="add_portfolio_name"]');
                    if (!addNameField.value.trim()) {
                        e.preventDefault();
                        alert('Portfolio name cannot be empty');
                    }
                } else if (action === 'rename') {
                    const oldName = document.querySelector('select[name="old_name"]').value;
                    const newName = document.querySelector('input[name="new_name"]').value.trim();
                    if (!oldName || !newName) {
                        e.preventDefault();
                        alert('Both old and new portfolio names are required');
                    }
                } else if (action === 'delete') {
                    const deleteNameField = document.querySelector('select[name="delete_portfolio_name"]');
                    if (!deleteNameField.value) {
                        e.preventDefault();
                        alert('Please select a portfolio to delete');
                    }
                }
            });
        }
    }
};

const LayoutManager = {
    adjustCardHeights() {
        const cards = document.querySelectorAll('.columns > .column > .card');
        let maxContentHeight = 0;
        let targetHeight = 200; // Reduced target height for more compactness
        
        // Reset heights to auto first to get natural content height
        cards.forEach(card => {
            card.style.height = 'auto';
        });
        
        // Find the maximum content height
        cards.forEach(card => {
            const height = card.offsetHeight;
            if (height > maxContentHeight) {
                maxContentHeight = height;
            }
        });
        
        // Use the larger of target height or content height
        const finalHeight = Math.max(targetHeight, maxContentHeight);
        
        // Apply the consistent height to all cards
        cards.forEach(card => {
            card.style.height = `${finalHeight}px`;
        });
    },
    
    init() {
        this.adjustCardHeights();
        
        // Adjust heights on window resize
        window.addEventListener('resize', this.adjustCardHeights);
    }
};

// Portfolio Table Vue Application
class PortfolioTableApp {
    constructor(portfolios, defaultPortfolio = "") {
        this.app = new Vue({
            el: '#portfolio-table-app',
            data() {
                return {
                    portfolioItems: [],
                    portfolioOptions: portfolios,
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
                    },
                    selectedPortfolio: defaultPortfolio,
                    showOnlyMissingPrices: false,
                    sortColumn: '',
                    sortDirection: 'asc'
                };
            },
            computed: {
                healthColorClass() {
                    if (!this.portfolioItems.length) return 'is-info';
                    const health = this.metrics.health;
                    if (health >= 90) return 'is-success';
                    if (health >= 70) return 'is-warning';
                    return 'is-danger';
                },
                filteredPortfolioItems() {
                    // First filter by selected portfolio
                    let filtered = this.selectedPortfolio 
                        ? this.portfolioItems.filter(item => item.portfolio === this.selectedPortfolio)
                        : this.portfolioItems;
                    
                    // Then filter by missing prices if checkbox is checked
                    if (this.showOnlyMissingPrices) {
                        filtered = filtered.filter(item => !item.price_eur);
                    }
                    
                    // Apply sorting if a sort column is specified
                    if (this.sortColumn) {
                        const direction = this.sortDirection === 'asc' ? 1 : -1;
                        
                        filtered = [...filtered].sort((a, b) => {
                            // Handle special cases for calculated fields
                            if (this.sortColumn === 'total_value') {
                                const aValue = (a.price_eur || 0) * (a.shares || 0);
                                const bValue = (b.price_eur || 0) * (b.shares || 0);
                                return direction * (aValue - bValue);
                            }
                            
                            // For regular fields
                            let aVal = a[this.sortColumn];
                            let bVal = b[this.sortColumn];
                            
                            // Handle null/undefined values
                            if (aVal === null || aVal === undefined) aVal = '';
                            if (bVal === null || bVal === undefined) bVal = '';
                            
                            // Convert to numbers for numeric fields
                            if (this.sortColumn === 'shares' || this.sortColumn === 'price_eur' || this.sortColumn === 'total_invested') {
                                aVal = parseFloat(aVal) || 0;
                                bVal = parseFloat(bVal) || 0;
                                return direction * (aVal - bVal);
                            }
                            
                            // Handle dates
                            if (this.sortColumn === 'last_updated') {
                                const aDate = aVal ? new Date(aVal) : new Date(0);
                                const bDate = bVal ? new Date(bVal) : new Date(0);
                                return direction * (aDate - bDate);
                            }
                            
                            // String comparison for text fields
                            return direction * String(aVal).localeCompare(String(bVal));
                        });
                    }
                    
                    return filtered;
                }
            },
            watch: {
                showOnlyMissingPrices() {
                    // Update metrics only if we're showing filtered data
                    this.updateFilteredMetrics();
                },
                selectedPortfolio() {
                    // Update metrics when portfolio selection changes
                    this.updateFilteredMetrics();
                }
            },
            methods: {
                async loadData() {
                    this.loading = true;
                    try {
                        // Load portfolio items
                        const response = await fetch('/portfolio/api/portfolio_data');
                        const data = await response.json();
                        this.portfolioItems = data;
                        console.log('Loaded portfolio items:', this.portfolioItems);
                        this.updateMetrics();
                        this.updateFilteredMetrics();
                        
                        // Also refresh the portfolio options at the same time
                        try {
                            const portfoliosResponse = await fetch('/portfolio/api/portfolios');
                            const portfoliosData = await portfoliosResponse.json();
                            if (Array.isArray(portfoliosData) && portfoliosData.length > 0) {
                                this.portfolioOptions = portfoliosData;
                                console.log('Updated portfolio options:', this.portfolioOptions);
                            } else {
                                console.warn('No portfolio options received or empty array');
                            }
                        } catch (portfolioError) {
                            console.error('Error refreshing portfolio options:', portfolioError);
                        }
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
        
                updateFilteredMetrics() {
                    const filteredItems = this.filteredPortfolioItems;
                    this.metrics = {
                        total: filteredItems.length,
                        health: filteredItems.length ? Math.round(((filteredItems.length - filteredItems.filter(i => !i.price_eur).length) / filteredItems.length) * 100) : 100,
                        missing: filteredItems.filter(i => !i.price_eur).length,
                        totalValue: filteredItems.reduce((sum, item) => sum + ((item.price_eur || 0) * (item.shares || 0)), 0),
                        lastUpdate: filteredItems.reduce((latest, item) => !latest || (item.last_updated && item.last_updated > latest) ? item.last_updated : latest, null)
                    };
                },
        
                confirmPriceUpdate(item) {
                    this.selectedItem = item;
                    // Instead of showing modal, directly update the price
                    this.updatePrice();
                },
        
                confirmDelete(item) {
                    this.selectedItem = item;
                    this.showDeleteModal = true;
                },
        
                closeModal() {
                    this.showUpdatePriceModal = false;
                    this.showDeleteModal = false;
                    this.selectedItem = {};
                },
        
                async updatePrice() {
                    if (!this.selectedItem.id) return;
                    
                    this.isUpdating = true;
                    try {
                        const response = await fetch(`/portfolio/api/update_price/${this.selectedItem.id}`, {
                            method: 'POST'
                        });
                        const result = await response.json();
                        
                        if (response.ok) {
                            // Refresh the data
                            await this.loadData();
                            
                            // Show success notification
                            if (typeof showNotification === 'function') {
                                showNotification(result.message || 'Price updated successfully', 'is-success');
                            } else {
                                console.log(result.message || 'Price updated successfully');
                            }
                        } else {
                            // Construct a meaningful error message
                            let errorMessage = result.error || 'Failed to update price';
                            
                            // If we have additional details, add them
                            if (result.details) {
                                errorMessage += `\n\n${result.details}`;
                                console.error('Detailed error:', result.details);
                            }
                            
                            // Show error notification
                            if (typeof showNotification === 'function') {
                                showNotification(errorMessage, 'is-danger');
                            } else {
                                console.error('Error:', errorMessage);
                            }
                        }
                    } catch (error) {
                        console.error('Error updating price:', error);
                        if (typeof showNotification === 'function') {
                            showNotification('Network error while updating price. Please try again.', 'is-danger');
                        }
                    } finally {
                        this.isUpdating = false;
                        // Reset the selected item after update is complete
                        this.selectedItem = {};
                    }
                },
        
                async deleteItem() {
                    if (!this.selectedItem.id) return;
                    
                    this.isDeleting = true;
                    try {
                        const response = await fetch(`/portfolio/api/company/${this.selectedItem.id}`, {
                            method: 'DELETE'
                        });
                        
                        const result = await response.json();
                        
                        if (response.ok) {
                            // Refresh the data
                            await this.loadData();
                            
                            // Show success notification
                            if (typeof showNotification === 'function') {
                                showNotification(result.message || 'Company deleted successfully', 'is-success');
                            } else {
                                console.log('Success:', result.message || 'Company deleted successfully');
                            }
                        } else {
                            // Show error notification
                            if (typeof showNotification === 'function') {
                                showNotification(result.error || 'Failed to delete company', 'is-danger');
                            } else {
                                console.error('Error:', result.error || 'Failed to delete company');
                            }
                        }
                    } catch (error) {
                        console.error('Error deleting item:', error);
                        if (typeof showNotification === 'function') {
                            showNotification('An error occurred while deleting the company', 'is-danger');
                        }
                    } finally {
                        this.isDeleting = false;
                        this.closeModal();
                    }
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
                                portfolio: item.portfolio || '-'
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
                            
                            // Trigger price update for this row after identifier change
                            console.log('Triggering price update after identifier change for item:', item.id);
                            try {
                                const priceResponse = await fetch(`/portfolio/api/update_price/${item.id}`, {
                                    method: 'POST'
                                });
                                
                                const priceResult = await priceResponse.json();
                                
                                if (priceResponse.ok) {
                                    // Refresh the data
                                    await this.loadData();
                                    
                                    // Show success notification
                                    if (typeof showNotification === 'function') {
                                        showNotification('Price updated after identifier change', 'is-success');
                                    } else {
                                        console.log('Price updated after identifier change');
                                    }
                                } else {
                                    // Show error notification
                                    if (typeof showNotification === 'function') {
                                        showNotification(priceResult.error || 'Failed to update price after identifier change', 'is-warning');
                                    } else {
                                        console.error('Error:', priceResult.error || 'Failed to update price after identifier change');
                                    }
                                }
                            } catch (priceError) {
                                console.error('Error updating price after identifier change:', priceError);
                                if (typeof showNotification === 'function') {
                                    showNotification('Error updating price after identifier change', 'is-warning');
                                }
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
                },
                
                // Sort table by column
                sortBy(column) {
                    // If clicking the same column, toggle direction
                    if (this.sortColumn === column) {
                        this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
                    } else {
                        // New column, default to ascending
                        this.sortColumn = column;
                        this.sortDirection = 'asc';
                    }
                    
                    console.log(`Sorting by ${column} in ${this.sortDirection} order`);
                }
            },
            mounted() {
                console.log('Vue component mounted. Methods available:', Object.keys(this.$options.methods).join(', '));
                console.log('Initial portfolio options:', this.portfolioOptions);
                
                // First, normalize the initial portfolioOptions if they exist
                console.log('Initial portfolio options type:', typeof this.portfolioOptions, Array.isArray(this.portfolioOptions));
                
                // Convert array of objects to array of strings if needed
                if (Array.isArray(this.portfolioOptions)) {
                    if (this.portfolioOptions.length > 0 && typeof this.portfolioOptions[0] === 'object' && this.portfolioOptions[0].name) {
                        console.log('Converting portfolio options from objects to strings');
                        this.portfolioOptions = this.portfolioOptions.map(p => p.name);
                    }
                    console.log('Normalized initial portfolio options:', this.portfolioOptions);
                }
                
                // Always fetch fresh portfolio data from the server
                console.log('Fetching up-to-date portfolio options from server...');
                fetch('/portfolio/api/portfolios')
                    .then(response => {
                        console.log('Portfolio API response status:', response.status);
                        if (!response.ok) {
                            throw new Error(`HTTP error ${response.status}`);
                        }
                        return response.json();
                    })
                    .then(data => {
                        console.log('Portfolio options from server (RAW):', data);
                        console.log('Portfolio options type:', typeof data, Array.isArray(data));
                        
                        if (Array.isArray(data)) {
                            // Use exactly what the API returns without additional filtering
                            this.portfolioOptions = data;
                            console.log('Updated portfolio options array:', this.portfolioOptions);
                            console.log('Individual portfolio options:');
                            this.portfolioOptions.forEach((option, index) => {
                                console.log(`Option ${index}:`, option, 'Type:', typeof option);
                            });
                            
                            // Check if we have valid portfolio options
                            if (this.portfolioOptions.length === 0) {
                                console.warn('No portfolio options found from server');
                            }
                            
                            // Log whether Default portfolio is in the options
                            const hasDefault = this.portfolioOptions.includes('Default');
                            console.log('Has Default portfolio in options:', hasDefault);
                        } else {
                            console.warn('Invalid portfolio options format from server');
                            this.portfolioOptions = [];
                        }
                    })
                    .catch(error => {
                        console.error('Error fetching portfolio options:', error);
                        // Fall back to options passed from template if API fails
                        if (Array.isArray(this.portfolioOptions)) {
                            console.log('Falling back to template-provided portfolio options');
                            this.portfolioOptions = this.portfolioOptions.filter(p => p && p !== '-');
                        } else {
                            this.portfolioOptions = [];
                        }
                    })
                    .finally(() => {
                        // Load all data after portfolio options are handled
                        this.loadData();
                    });
            }
        });
        
        return this.app;
    }
}

// Bulk Edit Vue Application
class BulkEditApp {
    constructor(portfolios) {
        console.log('Initializing BulkEditApp with portfolios:', JSON.stringify(portfolios));
        this.app = new Vue({
            el: '#bulk-edit-app',
            data() {
                return {
                    companies: [],
                    // Initialize directly with provided portfolios to avoid initial empty dropdown
                    portfolioOptions: Array.isArray(portfolios) ? [...portfolios] : ['-', 'crypto', 'dividend', 'value'],
                    staticPortfolios: Array.isArray(portfolios) ? [...portfolios] : [],
                    targetPortfolio: '',
                    portfolioAction: 'add',
                    activeTab: 'portfolio',
                    newCategory: '',
                    selectedCompanies: [],
                    searchQuery: '',
                    loading: false,
                    isLoading: false,
                    
                    // Portfolio management fields
                    addPortfolioName: '',
                    oldPortfolioName: '',
                    newPortfolioName: '',
                    deletePortfolioName: '',
                    isPortfolioLoading: false
                };
            },
            computed: {
                computedGroupedCompanies() {
                    // Group companies by portfolio
                    const grouped = {};
                    
                    // Ensure companies is an array before processing
                    if (!Array.isArray(this.companies) || this.companies.length === 0) {
                        console.log('No companies data available');
                        return {};
                    }
                    
                    // Filter companies by search query if provided
                    const filteredCompanies = this.searchQuery 
                        ? this.companies.filter(c => 
                            c.name?.toLowerCase().includes(this.searchQuery.toLowerCase()) || 
                            c.identifier?.toLowerCase().includes(this.searchQuery.toLowerCase()))
                        : this.companies;
                    
                    console.log(`Filtered ${filteredCompanies.length} companies from ${this.companies.length} total`);
                    
                    // Group by portfolio
                    filteredCompanies.forEach(company => {
                        const portfolio = company.portfolio || 'Unassigned';
                        if (!grouped[portfolio]) {
                            grouped[portfolio] = [];
                        }
                        grouped[portfolio].push(company);
                    });
                    
                    // Sort companies alphabetically within each portfolio
                    for (const portfolio in grouped) {
                        grouped[portfolio].sort((a, b) => (a.name || '').localeCompare(b.name || ''));
                    }
                    
                    return grouped;
                }
            },
            methods: {
                async loadPortfolioOptions() {
                    try {
                        console.log('Fetching up-to-date portfolio options from server...');
                        console.log('Current portfolioOptions before fetch:', JSON.stringify(this.portfolioOptions));
                        
                        console.log('Starting API call to fetch portfolios...');
                        const response = await fetch('/portfolio/api/portfolios');
                        console.log('Portfolio API response status:', response.status);
                        
                        if (!response.ok) {
                            throw new Error(`HTTP error ${response.status}`);
                        }
                        
                        console.log('Parsing JSON response...');
                        const data = await response.json();
                        console.log('Portfolio options from server (RAW):', JSON.stringify(data));
                        console.log('Portfolio options type:', typeof data, Array.isArray(data));
                        
                        // If no data is returned, just use an empty array with the default option
                        if (!Array.isArray(data) || data.length === 0) {
                            console.warn('No portfolios returned from server');
                            // Only include the default portfolio option
                            this.portfolioOptions = ['-'];
                            return;
                        }
                        
                        // Reset portfolioOptions to empty array to avoid mutation issues
                        this.portfolioOptions = [];
                        
                        // Create a new array for portfolio options
                        let newOptions = [];
                        
                        // Debugging information
                        const itemsWithValues = [];
                        data.forEach((item, idx) => {
                            itemsWithValues.push(`Item ${idx}: [${item}] type=${typeof item}`);
                        });
                        console.log('All items with values:', itemsWithValues.join(', '));
                        
                        // Filter out any null, undefined or empty strings
                        newOptions = data.filter(item => item !== null && item !== undefined && item !== '');
                        
                        // Make sure we have the default portfolio option
                        if (!newOptions.includes('-')) {
                            newOptions.unshift('-'); // Add Default portfolio at the beginning
                        }
                        
                        // Log the new options
                        console.log('Processed new portfolio options:', JSON.stringify(newOptions));
                        console.log('Number of portfolio options:', newOptions.length);
                        console.log('Individual portfolio options:');
                        newOptions.forEach((option, index) => {
                            console.log(`Option ${index}:`, option, 'Type:', typeof option);
                        });
                        
                        // Update the data property with the new array
                        this.portfolioOptions = newOptions;
                        
                        console.log('Updated portfolioOptions in Vue data:', JSON.stringify(this.portfolioOptions));
                        console.log('Number of options in Vue data:', this.portfolioOptions.length);
                        
                        // Force Vue to update the UI
                        this.$nextTick(() => {
                            console.log('Next tick, forcing update...');
                            this.$forceUpdate();
                            console.log('Vue UI updated with force update');
                        });
                    } catch (err) {
                        console.error('Error fetching portfolio options:', err);
                        // Fall back to default option if API fails
                        console.warn('Using fallback portfolio options due to error');
                        this.portfolioOptions = ['-', 'crypto', 'dividend', 'value']; // Add some sensible defaults for testing
                        this.$forceUpdate();
                    }
                },
                
                async loadCompanies() {
                    console.log('Starting to load companies');
                    this.loading = true;
                    try {
                        console.log('Fetching from /portfolio/api/portfolio_data');
                        const response = await fetch('/portfolio/api/portfolio_data');
                        console.log('Response received:', response);
                        if (!response.ok) {
                            throw new Error(`Failed to load companies: ${response.status} ${response.statusText}`);
                        }
                        const data = await response.json();
                        console.log('Data received:', data ? `${data.length} items` : 'no data');
                        
                        // Map the data to ensure it has the correct structure
                        if (Array.isArray(data)) {
                            this.companies = data.map(item => ({
                                id: item.id,
                                name: item.company || '',
                                identifier: item.identifier || '',
                                portfolio: item.portfolio || '',
                                category: item.category || ''
                            }));
                            console.log('Processed company data:', this.companies.length, 'items');
                        } else {
                            console.error('Received non-array data:', data);
                            this.companies = []; // Ensure we have an empty array even on error
                        }
                    } catch (err) {
                        console.error('Error loading companies:', err);
                        this.companies = []; // Ensure we have an empty array even on error
                    } finally {
                        console.log('Finished loading companies, setting loading to false');
                        this.loading = false;
                    }
                },
                
                isPortfolioSelected(portfolio) {
                    // Check if all companies in this portfolio are selected
                    const companiesInPortfolio = this.computedGroupedCompanies[portfolio] || [];
                    if (!companiesInPortfolio.length) return false;
                    
                    return companiesInPortfolio.every(company => 
                        this.selectedCompanies.includes(company.id));
                },
                
                togglePortfolio(portfolio) {
                    const companiesInPortfolio = this.computedGroupedCompanies[portfolio] || [];
                    const allSelected = this.isPortfolioSelected(portfolio);
                    
                    if (allSelected) {
                        // Deselect all companies in this portfolio
                        this.selectedCompanies = this.selectedCompanies.filter(id => 
                            !companiesInPortfolio.some(company => company.id === id));
                    } else {
                        // Select all companies in this portfolio
                        const companyIds = companiesInPortfolio.map(company => company.id);
                        this.selectedCompanies = [...new Set([...this.selectedCompanies, ...companyIds])];
                    }
                },
                
                closeModal() {
                    // Close the bulk edit modal
                    const modal = document.getElementById('bulk-edit-modal');
                    if (modal) {
                        modal.classList.remove('is-active');
                        document.documentElement.classList.remove('is-clipped');
                        
                        // Reload the portfolio data table to see the latest updates
                        if (window.portfolioTableApp && typeof window.portfolioTableApp.loadData === 'function') {
                            console.log('Reloading portfolio data table after closing bulk edit modal');
                            window.portfolioTableApp.loadData();
                        } else {
                            console.warn('Could not find portfolioTableApp to reload data');
                        }
                    }
                },
                
                openModal() {
                    // Open the bulk edit modal and refresh data
                    this.loadCompanies(); // Reload companies data
                    const modal = document.getElementById('bulk-edit-modal');
                    if (modal) {
                        modal.classList.add('is-active');
                        document.documentElement.classList.add('is-clipped');
                    }
                },
                
                async applyPortfolioChanges() {
                    // Apply portfolio changes to all selected companies
                    if (this.selectedCompanies.length === 0) {
                        if (typeof showNotification === 'function') {
                            showNotification('Please select at least one company', 'is-warning');
                        } else {
                            alert('Please select at least one company');
                        }
                        return;
                    }
                    
                    if (!this.targetPortfolio) {
                        if (typeof showNotification === 'function') {
                            showNotification('Please select a target portfolio', 'is-warning');
                        } else {
                            alert('Please select a target portfolio');
                        }
                        return;
                    }
                    
                    try {
                        // Set loading state
                        this.isLoading = true;
                        
                        // Call the bulk update API endpoint
                        const response = await fetch('/portfolio/api/bulk_update', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({
                                companies: this.selectedCompanies,
                                portfolio: this.targetPortfolio
                            })
                        });
                        
                        if (!response.ok) {
                            throw new Error(`Network response was not ok: ${response.status}`);
                        }
                        
                        const result = await response.json();
                        
                        if (result.success) {
                            if (typeof showNotification === 'function') {
                                showNotification(result.message, 'is-success');
                            } else {
                                alert(result.message);
                            }
                            
                            // Refresh the companies
                            await this.loadCompanies();
                        } else {
                            throw new Error(result.error || 'Failed to update companies');
                        }
                    } catch (error) {
                        console.error('Error applying portfolio changes:', error);
                        if (typeof showNotification === 'function') {
                            showNotification(error.message, 'is-danger');
                        } else {
                            alert(`Error: ${error.message}`);
                        }
                    } finally {
                        this.isLoading = false;
                    }
                },
                
                async applyCategoryChanges() {
                    // Apply category changes to all selected companies
                    if (this.selectedCompanies.length === 0) {
                        if (typeof showNotification === 'function') {
                            showNotification('Please select at least one company', 'is-warning');
                        } else {
                            alert('Please select at least one company');
                        }
                        return;
                    }
                    
                    // Check for undefined, null, or empty string
                    // Allow explicitly setting empty string as a valid category
                    if (this.newCategory === undefined || this.newCategory === null) {
                        if (typeof showNotification === 'function') {
                            showNotification('Please enter a category name', 'is-warning');
                        } else {
                            alert('Please enter a category name');
                        }
                        return;
                    }
                    
                    try {
                        // Set loading state
                        this.isLoading = true;
                        
                        // Call the bulk update API endpoint
                        const response = await fetch('/portfolio/api/bulk_update', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({
                                companies: this.selectedCompanies,
                                category: this.newCategory
                            })
                        });
                        
                        if (!response.ok) {
                            throw new Error(`Network response was not ok: ${response.status}`);
                        }
                        
                        const result = await response.json();
                        
                        if (result.success) {
                            if (typeof showNotification === 'function') {
                                showNotification(result.message, 'is-success');
                            } else {
                                alert(result.message);
                            }
                            
                            // Refresh the companies
                            await this.loadCompanies();
                        } else {
                            throw new Error(result.error || 'Failed to update companies');
                        }
                    } catch (error) {
                        console.error('Error applying category changes:', error);
                        if (typeof showNotification === 'function') {
                            showNotification(error.message, 'is-danger');
                        } else {
                            alert(`Error: ${error.message}`);
                        }
                    } finally {
                        this.isLoading = false;
                    }
                },
                
                // Portfolio management methods
                async addPortfolio() {
                    if (!this.addPortfolioName.trim()) {
                        if (typeof showNotification === 'function') {
                            showNotification('Portfolio name cannot be empty', 'is-warning');
                        } else {
                            alert('Portfolio name cannot be empty');
                        }
                        return;
                    }
                    
                    this.isPortfolioLoading = true;
                    try {
                        // Create form data to match the server endpoint
                        const formData = new FormData();
                        formData.append('action', 'add');
                        formData.append('add_portfolio_name', this.addPortfolioName);
                        
                        // Send request to create portfolio
                        const response = await fetch('/portfolio/manage_portfolios', {
                            method: 'POST',
                            body: formData
                        });
                        
                        if (!response.ok) {
                            throw new Error(`Server returned ${response.status}: ${response.statusText}`);
                        }
                        
                        // Success notification
                        if (typeof showNotification === 'function') {
                            showNotification(`Portfolio "${this.addPortfolioName}" created successfully`, 'is-success');
                        } else {
                            alert(`Portfolio "${this.addPortfolioName}" created successfully`);
                        }
                        
                        // Store the new portfolio name
                        const newPortfolio = this.addPortfolioName;
                        
                        // Reset form
                        this.addPortfolioName = '';
                        
                        // Add the new portfolio to the local portfolioOptions array immediately
                        if (!this.portfolioOptions.includes(newPortfolio)) {
                            this.portfolioOptions.push(newPortfolio);
                            // Sort the portfolios alphabetically
                            this.portfolioOptions.sort();
                            console.log('Added new portfolio to options, new options:', this.portfolioOptions);
                        }
                        
                        // Then refresh from server to ensure everything is in sync
                        await this.loadPortfolioOptions();
                        
                    } catch (error) {
                        console.error('Error creating portfolio:', error);
                        if (typeof showNotification === 'function') {
                            showNotification(`Error creating portfolio: ${error.message}`, 'is-danger');
                        } else {
                            alert(`Error creating portfolio: ${error.message}`);
                        }
                    } finally {
                        this.isPortfolioLoading = false;
                    }
                },
                
                async renamePortfolio() {
                    if (!this.oldPortfolioName || !this.newPortfolioName.trim()) {
                        if (typeof showNotification === 'function') {
                            showNotification('Both old and new portfolio names are required', 'is-warning');
                        } else {
                            alert('Both old and new portfolio names are required');
                        }
                        return;
                    }
                    
                    this.isPortfolioLoading = true;
                    try {
                        // Create form data to match the server endpoint
                        const formData = new FormData();
                        formData.append('action', 'rename');
                        formData.append('old_name', this.oldPortfolioName);
                        formData.append('new_name', this.newPortfolioName);
                        
                        // Send request to rename portfolio
                        const response = await fetch('/portfolio/manage_portfolios', {
                            method: 'POST',
                            body: formData
                        });
                        
                        if (!response.ok) {
                            throw new Error(`Server returned ${response.status}: ${response.statusText}`);
                        }
                        
                        // Success notification
                        if (typeof showNotification === 'function') {
                            showNotification(`Portfolio renamed from "${this.oldPortfolioName}" to "${this.newPortfolioName}"`, 'is-success');
                        } else {
                            alert(`Portfolio renamed from "${this.oldPortfolioName}" to "${this.newPortfolioName}"`);
                        }
                        
                        // Store old and new names for reference
                        const oldName = this.oldPortfolioName;
                        const newName = this.newPortfolioName;
                        
                        // Reset form fields
                        this.oldPortfolioName = '';
                        this.newPortfolioName = '';
                        
                        // Update any selections that used the old name
                        if (this.targetPortfolio === oldName) {
                            console.log('Updating targetPortfolio selection to new name');
                            this.targetPortfolio = newName;
                        }
                        
                        // Update the local portfolioOptions array immediately
                        this.portfolioOptions = this.portfolioOptions.filter(p => p !== oldName);
                        if (!this.portfolioOptions.includes(newName)) {
                            this.portfolioOptions.push(newName);
                            // Sort the portfolios alphabetically
                            this.portfolioOptions.sort();
                        }
                        console.log('Updated portfolio options after rename:', this.portfolioOptions);
                        
                        // Then refresh from server to ensure everything is in sync
                        await this.loadPortfolioOptions();
                        await this.loadCompanies(); // Reload companies to update portfolio names
                        
                    } catch (error) {
                        console.error('Error renaming portfolio:', error);
                        if (typeof showNotification === 'function') {
                            showNotification(`Error renaming portfolio: ${error.message}`, 'is-danger');
                        } else {
                            alert(`Error renaming portfolio: ${error.message}`);
                        }
                    } finally {
                        this.isPortfolioLoading = false;
                    }
                },
                
                async deletePortfolio() {
                    if (!this.deletePortfolioName) {
                        if (typeof showNotification === 'function') {
                            showNotification('Please select a portfolio to delete', 'is-warning');
                        } else {
                            alert('Please select a portfolio to delete');
                        }
                        return;
                    }
                    
                    // Confirm deletion
                    if (!confirm(`Are you sure you want to delete the portfolio "${this.deletePortfolioName}"? This cannot be undone.`)) {
                        return;
                    }
                    
                    this.isPortfolioLoading = true;
                    try {
                        // Create form data to match the server endpoint
                        const formData = new FormData();
                        formData.append('action', 'delete');
                        formData.append('delete_portfolio_name', this.deletePortfolioName);
                        
                        // Send request to delete portfolio
                        const response = await fetch('/portfolio/manage_portfolios', {
                            method: 'POST',
                            body: formData
                        });
                        
                        if (!response.ok) {
                            throw new Error(`Server returned ${response.status}: ${response.statusText}`);
                        }
                        
                        // Success notification
                        if (typeof showNotification === 'function') {
                            showNotification(`Portfolio "${this.deletePortfolioName}" deleted successfully`, 'is-success');
                        } else {
                            alert(`Portfolio "${this.deletePortfolioName}" deleted successfully`);
                        }
                        
                        // Store the deleted portfolio name for reference
                        const deletedPortfolio = this.deletePortfolioName;
                        
                        // Reset all portfolio selections if they match the deleted portfolio
                        if (this.targetPortfolio === deletedPortfolio) {
                            console.log('Resetting targetPortfolio as it was deleted');
                            this.targetPortfolio = '';
                        }
                        if (this.oldPortfolioName === deletedPortfolio) {
                            console.log('Resetting oldPortfolioName as it was deleted');
                            this.oldPortfolioName = '';
                        }
                        
                        // Reset delete form field
                        this.deletePortfolioName = '';
                        
                        // Remove the deleted portfolio from the local portfolioOptions array immediately
                        this.portfolioOptions = this.portfolioOptions.filter(p => p !== deletedPortfolio);
                        console.log('Removed deleted portfolio from options, new options:', this.portfolioOptions);
                        
                        // Then refresh from server to ensure everything is in sync
                        await this.loadPortfolioOptions();
                        
                    } catch (error) {
                        console.error('Error deleting portfolio:', error);
                        if (typeof showNotification === 'function') {
                            showNotification(`Error deleting portfolio: ${error.message}`, 'is-danger');
                        } else {
                            alert(`Error deleting portfolio: ${error.message}`);
                        }
                    } finally {
                        this.isPortfolioLoading = false;
                    }
                }
            },
            mounted() {
                console.log('Bulk edit app mounted, loading data...');
                
                // Ensure we load the portfolio options when the component is mounted
                // This is crucial for the modal dropdowns to work properly
                this.loadPortfolioOptions().then(() => {
                    console.log('Portfolio options loaded in mounted hook:', JSON.stringify(this.portfolioOptions));
                });
                
                // Log initial state
                console.log('Initial portfolioOptions:', JSON.stringify(this.portfolioOptions));
                console.log('Initial staticPortfolios:', JSON.stringify(this.staticPortfolios));
                
                // Make sure we have default portfolio in the initial options
                if (Array.isArray(this.portfolioOptions) && this.portfolioOptions.length > 0) {
                    if (!this.portfolioOptions.includes('-')) {
                        this.portfolioOptions.unshift('-'); // Add Default at beginning
                        console.log('Added Default portfolio to initial options');
                    }
                } else if (Array.isArray(this.portfolioOptions) && this.portfolioOptions.length === 0) {
                    this.portfolioOptions = ['-']; // Initialize with Default
                    console.log('Initialized empty portfolioOptions with Default');
                }
                
                // Log the updated initial state
                console.log('Updated initial portfolioOptions:', JSON.stringify(this.portfolioOptions));
                
                // Load portfolios and companies
                this.loadPortfolioOptions();
                this.loadCompanies();
                
                // Additional logging to debug
                setTimeout(() => {
                    console.log('After timeout, portfolioOptions:', JSON.stringify(this.portfolioOptions));
                    // Force update the component to ensure dropdown is refreshed
                    this.$forceUpdate();
                }, 1000);
                
                // Connect close button in the modal footer
                const saveButton = document.getElementById('bulk-edit-save');
                if (saveButton) {
                    saveButton.addEventListener('click', this.closeModal.bind(this));
                }
            }
        });
        
        // Make it globally available for the portfolio table app to access
        window.bulkEditApp = this.app;
        
        return this.app;
    }
}

// Portfolio Modal Management functionality
const ModalPortfolioManager = {
    updatePortfolioFields(action) {
        // Hide all fields first
        document.getElementById('modal-add-portfolio-fields').classList.add('is-hidden');
        document.getElementById('modal-rename-portfolio-fields').classList.add('is-hidden');
        document.getElementById('modal-delete-portfolio-fields').classList.add('is-hidden');
        
        // Enable/disable action button
        const actionButton = document.getElementById('modal-portfolio-action-btn');
        actionButton.disabled = !action;
        
        // Show relevant fields based on action
        if (action === 'add') {
            document.getElementById('modal-add-portfolio-fields').classList.remove('is-hidden');
        } else if (action === 'rename') {
            document.getElementById('modal-rename-portfolio-fields').classList.remove('is-hidden');
        } else if (action === 'delete') {
            document.getElementById('modal-delete-portfolio-fields').classList.remove('is-hidden');
        }
    },
    
    init() {
        const modalActionSelect = document.getElementById('modal-portfolio-action');
        const modalPortfolioForm = document.getElementById('modal-manage-portfolios-form');
        
        if (modalActionSelect) {
            modalActionSelect.addEventListener('change', function() {
                ModalPortfolioManager.updatePortfolioFields(this.value);
            });
        }
        
        if (modalPortfolioForm) {
            modalPortfolioForm.addEventListener('submit', function(e) {
                const action = document.getElementById('modal-portfolio-action').value;
                
                if (action === 'add') {
                    const addNameField = document.querySelector('#modal-add-portfolio-fields input[name="add_portfolio_name"]');
                    if (!addNameField.value.trim()) {
                        e.preventDefault();
                        alert('Portfolio name cannot be empty');
                    }
                } else if (action === 'rename') {
                    const oldName = document.querySelector('#modal-rename-portfolio-fields select[name="old_name"]').value;
                    const newName = document.querySelector('#modal-rename-portfolio-fields input[name="new_name"]').value.trim();
                    if (!oldName || !newName) {
                        e.preventDefault();
                        alert('Both old and new portfolio names are required');
                    }
                } else if (action === 'delete') {
                    const deleteNameField = document.querySelector('#modal-delete-portfolio-fields select[name="delete_portfolio_name"]');
                    if (!deleteNameField.value) {
                        e.preventDefault();
                        alert('Please select a portfolio to delete');
                    }
                }
            });
        }
    }
};

// Main initialization function
document.addEventListener('DOMContentLoaded', function() {
    // Initialize all components
    FileUploadHandler.init();
    PortfolioManager.init();
    LayoutManager.init();
    ModalPortfolioManager.init();
    
    // Get portfolios data from the template
    const portfoliosElement = document.getElementById('portfolios-data');
    let portfolios = [];
    let defaultPortfolio = "";
    
    if (portfoliosElement) {
        try {
            portfolios = JSON.parse(portfoliosElement.textContent);
            console.log('Parsed portfolios from DOM:', portfolios);
        } catch (error) {
            console.error('Error parsing portfolios data:', error);
        }
    } else {
        console.warn('No portfolios-data element found in DOM');
    }
    
    // Check for default portfolio setting
    const defaultPortfolioElement = document.getElementById('default-portfolio');
    if (defaultPortfolioElement) {
        defaultPortfolio = defaultPortfolioElement.textContent === 'true' ? '-' : '';
    }
    
    // Initialize Vue apps (if their mount points exist)
    if (document.getElementById('portfolio-table-app')) {
        // Create global portfolioTableApp instance to ensure it's accessible outside this scope
        window.portfolioTableApp = new PortfolioTableApp(portfolios, defaultPortfolio);
        
        // Log that the app has been initialized
        console.log('PortfolioTableApp initialized globally as window.portfolioTableApp');
    }
    
    if (document.getElementById('bulk-edit-app')) {
        // Create global bulkEditApp instance to ensure it's accessible outside this scope
        window.bulkEditApp = new BulkEditApp(portfolios);
        
        // Log that the app has been initialized
        console.log('BulkEditApp initialized globally as window.bulkEditApp');
    }
});