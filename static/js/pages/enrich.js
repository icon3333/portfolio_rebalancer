/**
 * Portfolio Enrichment Page JavaScript
 * Handles file uploads, portfolio management, and data visualization
 */

// DOM Elements and Utility Functions
const FileUploadHandler = {
    init() {
        const fileInput = document.querySelector('.file-input');
        const fileLabel = document.querySelector('.file-name');
        const uploadButton = document.getElementById('upload-button');
        const progressElement = document.getElementById('price-fetch-progress');
        const progressCount = document.getElementById('progress-count');
        const progressTotal = document.getElementById('progress-total');
        const progressPercentage = document.getElementById('progress-percentage');
        const uploadForm = document.querySelector('form[action*="upload"]');
        
        if (!fileInput || !fileLabel || !uploadButton) {
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
                uploadButton.disabled = false;
            } else {
                fileLabel.textContent = 'No file selected';
                uploadButton.disabled = true;
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
                progressElement.style.display = 'inline-flex';
                progressElement.dataset.processing = 'true';
                
                // Clear any existing interval and start a new one
                if (this.progressInterval) {
                    clearInterval(this.progressInterval);
                }
                
                // Create a new interval with more frequent updates during processing
                this.progressInterval = setInterval(() => {
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
                    progressBar.style.width = percentage + '%';
                }
                
                // Only show the progress indicator if there's actual progress happening
                // or if we're in processing mode (set by form submission)
                if (data.total > 0 || progressElement.dataset.processing === 'true') {
                    progressElement.style.display = 'inline-flex';
                    progressElement.style.flexDirection = 'column'; // Stack elements vertically
                    
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
                    showOnlyMissingPrices: false
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
                        const response = await fetch('/portfolio/api/portfolio_data');
                        const data = await response.json();
                        this.portfolioItems = data;
                        this.updateMetrics();
                        this.updateFilteredMetrics();
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
                    this.showUpdatePriceModal = true;
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
                                showNotification('Price updated successfully', 'is-success');
                            } else {
                                console.log('Price updated successfully');
                            }
                        } else {
                            // Show error notification
                            if (typeof showNotification === 'function') {
                                showNotification(result.error || 'Failed to update price', 'is-danger');
                            } else {
                                console.error('Error:', result.error || 'Failed to update price');
                            }
                        }
                    } catch (error) {
                        console.error('Error updating price:', error);
                        if (typeof showNotification === 'function') {
                            showNotification('Error updating price', 'is-danger');
                        }
                    } finally {
                        this.isUpdating = false;
                        this.closeModal();
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
        
        return this.app;
    }
}

// Bulk Edit Vue Application
class BulkEditApp {
    constructor(portfolios) {
        this.app = new Vue({
            el: '#bulk-edit-app',
            data() {
                return {
                    companies: [],
                    portfolioOptions: portfolios,
                    targetPortfolio: '',
                    portfolioAction: 'add',
                    activeTab: 'portfolio',
                    newCategory: '',
                    selectedCompanies: [],
                    searchQuery: '',
                    loading: false,
                    isLoading: false
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
                    // This is now a no-op as portfolios are initialized from server-side data
                    try {
                        console.log('Portfolio options already loaded:', this.portfolioOptions);
                    } catch (err) {
                        console.error('Error with portfolio options:', err);
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
                            
                            // Refresh the companies table
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
                        
                        // Don't reset selected companies here to allow multiple updates
                        // this.selectedCompanies = [];
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
                            
                            // Refresh the companies table
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
                        
                        // Don't reset selected companies here to allow multiple updates
                        // this.selectedCompanies = [];
                    }
                }
            },
            mounted() {
                console.log('Bulk edit app mounted, loading data...');
                this.loadPortfolioOptions();
                this.loadCompanies();
                
                // Connect close button in the modal footer
                const saveButton = document.getElementById('bulk-edit-save');
                if (saveButton) {
                    saveButton.addEventListener('click', this.closeModal.bind(this));
                }
                
                // We no longer need to connect the Apply Changes buttons here
                // as they are now handled directly through Vue @click directives in the template
            }
        });
        
        // Make it globally available for the portfolio table app to access
        window.bulkEditApp = this.app;
        
        return this.app;
    }
}

// Main initialization function
document.addEventListener('DOMContentLoaded', function() {
    // Initialize all components
    FileUploadHandler.init();
    PortfolioManager.init();
    LayoutManager.init();
    
    // Get portfolios data from the template
    const portfoliosElement = document.getElementById('portfolios-data');
    let portfolios = [];
    let defaultPortfolio = "";
    
    if (portfoliosElement) {
        try {
            portfolios = JSON.parse(portfoliosElement.textContent);
        } catch (error) {
            console.error('Error parsing portfolios data:', error);
        }
    }
    
    // Check for default portfolio setting
    const defaultPortfolioElement = document.getElementById('default-portfolio');
    if (defaultPortfolioElement) {
        defaultPortfolio = defaultPortfolioElement.textContent === 'true' ? '-' : '';
    }
    
    // Initialize Vue apps (if their mount points exist)
    if (document.getElementById('portfolio-table-app')) {
        const portfolioApp = new PortfolioTableApp(portfolios, defaultPortfolio);
    }
    
    if (document.getElementById('bulk-edit-app')) {
        const bulkEditApp = new BulkEditApp(portfolios);
    }
});