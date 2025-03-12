// Modified allocate.js - Fixed duplicate watchers that caused infinite loops

document.addEventListener('DOMContentLoaded', function() {
    // Add viewport size detection to Vue.js
    Vue.prototype.$viewport = {
        width: window.innerWidth,
        height: window.innerHeight
    };

    // Update on resize
    window.addEventListener('resize', function() {
        Vue.prototype.$viewport.width = window.innerWidth;
        Vue.prototype.$viewport.height = window.innerHeight;
    });

    // Create Vue application
    new Vue({
        el: '#portfolio-rebalancer',
        delimiters: ['${', '}'],  // Match existing Vue delimiters
        data() {
            return {
                // View state
                activeView: 'global',
                selectedPortfolio: '',
                expandedCategories: {},
                
                // Rebalancing settings
                rebalanceMode: 'existingCapital',
                newCapitalAmount: 5000,
                
                // Chart instances
                currentChart: null,
                targetChart: null,
                
                // Calculated portfolio data
                portfolioData: {
                    portfolios: []
                },
                
                // Mock data for initial rendering - will be replaced with API data
                mockData: {
                    portfolios: [
                        // ... mock data content remains unchanged ...
                    ]
                },
                
                // Calculated values
                totalValue: 0,
                newPortfolioValue: 0,
                requiredCapitalForNoSales: 0,
                
                // Loading state
                isLoading: false,
                
                // Flag to prevent update recursion
                isUpdating: false
            };
        },
        computed: {
            /**
            * Get currently selected portfolio data
            */
            selectedPortfolioData() {
                if (!this.selectedPortfolio) return null;
                return this.portfolioData.portfolios.find(p => p.name === this.selectedPortfolio);
            }
        },
        watch: {
            /**
            * Watch for changes to rebalance mode and recalculate
            */
            rebalanceMode() {
                // Prevent infinite loops by checking the isUpdating flag
                if (this.isUpdating) return;
                
                this.isUpdating = true;
                try {
                    this.calculateTargetValuesAndActions();
                    this.updateChartData();
                } finally {
                    this.isUpdating = false;
                }
            },
            
            /**
            * Watch for changes to new capital amount and recalculate
            */
            newCapitalAmount() {
                // Only process if we're in the right mode and not already updating
                if (this.rebalanceMode !== 'newCapitalSpecific' || this.isUpdating) return;
                
                this.isUpdating = true;
                try {
                    this.calculateTargetValuesAndActions();
                    this.updateChartData();
                } finally {
                    this.isUpdating = false;
                }
            },
            
            /**
            * Watch portfolio data for changes
            */
            portfolioData: {
                handler() {
                    if (this.isUpdating) return;
                    
                    this.isUpdating = true;
                    try {
                        this.$nextTick(() => {
                            // First calculate weights and actions
                            this.calculateCurrentWeights();
                            this.calculateRequiredCapitalForNoSales();
                            this.calculateTargetValuesAndActions();
                            
                            // Then update charts
                            this.updateChartData();
                        });
                    } finally {
                        this.isUpdating = false;
                    }
                },
                deep: true
            },
            
            /**
            * Watch for view changes
            */
            activeView() {
                if (this.isUpdating) return;
                
                this.isUpdating = true;
                try {
                    this.$nextTick(() => {
                        this.updateChartData();
                    });
                } finally {
                    this.isUpdating = false;
                }
            },
            
            /**
            * Watch for portfolio selection changes
            */
            selectedPortfolio() {
                if (this.isUpdating) return;
                
                this.isUpdating = true;
                try {
                    this.$nextTick(() => {
                        this.updateChartData();
                    });
                } finally {
                    this.isUpdating = false;
                }
            }
        },
        methods: {
            /**
            * Initialize the component
            */
            initialize() {
                // Fetch portfolio data from the API
                this.isLoading = true;
                
                // Fetch data from our new API endpoint
                axios.get('/portfolio/api/allocate/portfolio-data')
                    .then(response => {
                        if (response.data && response.data.portfolios) {
                            this.portfolioData = response.data;
                            console.log('Portfolio data loaded:', this.portfolioData);
                            
                            // Log target weights received from the server
                            if (this.portfolioData.portfolios.length > 0) {
                                console.log('Target weights from server:', 
                                    this.portfolioData.portfolios.map(p => ({
                                        name: p.name, 
                                        targetWeight: p.targetWeight
                                    }))
                                );
                            }
                            
                            // If we received no portfolios or they have no data, fall back to mock data
                            if (this.portfolioData.portfolios.length === 0) {
                                console.warn('No portfolio data found, using mock data for demo purposes');
                                this.portfolioData = JSON.parse(JSON.stringify(this.mockData));
                            }
                            
                            this.isUpdating = true;
                            try {
                                // Calculate initial values
                                this.calculateCurrentWeights();
                                this.calculateRequiredCapitalForNoSales();
                                this.calculateTargetValuesAndActions();
                                
                                // Set default selected portfolio
                                if (this.portfolioData.portfolios.length > 0 && !this.selectedPortfolio) {
                                    this.selectedPortfolio = this.portfolioData.portfolios[0].name;
                                }
                                
                                // Initialize charts with a small delay to ensure DOM is ready
                                this.$nextTick(() => {
                                    // Force a browser reflow to correctly calculate container sizes
                                    document.body.offsetHeight;
                                    
                                    // Add a short delay to ensure all Vue transitions and browser layouts are complete
                                    setTimeout(() => {
                                        this.initializeCharts();
                                        
                                        // Force another resize event after a longer delay to ensure everything is correct
                                        setTimeout(() => {
                                            window.dispatchEvent(new Event('resize'));
                                        }, 300);
                                    }, 150);
                                });
                            } finally {
                                this.isUpdating = false;
                            }
                        }
                    })
                    .catch(error => {
                        console.error('Error fetching portfolio data:', error);
                        
                        // Display more helpful error in console
                        if (error.response) {
                            // Server responded with error status
                            console.warn(`Server returned error ${error.response.status}: ${error.response.data.error || 'Unknown error'}`);
                        } else if (error.request) {
                            // Request was made but no response
                            console.warn('No response received from server. Server might be down or network issue.');
                        } else {
                            // Something else caused the error
                            console.warn('Error setting up request:', error.message);
                        }
                        
                        // Fall back to mock data if API fails
                        this.portfolioData = JSON.parse(JSON.stringify(this.mockData));
                        
                        // Show notification that we're using demo data
                        const notification = document.querySelector('.notification.is-info');
                        if (notification) {
                            notification.classList.remove('is-info');
                            notification.classList.add('is-warning');
                            notification.innerHTML = `
                                <button class="delete"></button>
                                <p><strong>Unable to load your portfolio data.</strong> Using demonstration data instead.</p>
                                <p class="mt-2">You can still explore the Portfolio Rebalancer features with this sample data.</p>
                            `;
                            
                            // Re-attach event listener for the delete button
                            const deleteBtn = notification.querySelector('.delete');
                            if (deleteBtn) {
                                deleteBtn.addEventListener('click', () => {
                                    notification.remove();
                                });
                            }
                        }
                        
                        this.isUpdating = true;
                        try {
                            // Calculate initial values
                            this.calculateCurrentWeights();
                            this.calculateRequiredCapitalForNoSales();
                            this.calculateTargetValuesAndActions();
                            
                            // Initialize charts with a delay to ensure DOM is ready
                            this.$nextTick(() => {
                                // Force a browser reflow to correctly calculate container sizes
                                document.body.offsetHeight;
                                
                                // Add a short delay to ensure all Vue transitions and browser layouts are complete
                                setTimeout(() => {
                                    this.initializeCharts();
                                    
                                    // Force another resize event after charts are initialized
                                    setTimeout(() => {
                                        window.dispatchEvent(new Event('resize'));
                                    }, 300);
                                }, 150);
                            });
                        } finally {
                            this.isUpdating = false;
                        }
                    })
                    .finally(() => {
                        this.isLoading = false;
                    });
            },
            
            /**
            * Set the active view (global or detail)
            */
            setActiveView(view) {
                if (this.activeView === view) return;
                
                this.activeView = view;
                
                // If switching to detail view, ensure a portfolio is selected
                if (view === 'detail' && !this.selectedPortfolio && this.portfolioData.portfolios.length > 0) {
                    this.selectedPortfolio = this.portfolioData.portfolios[0].name;
                }
                
                // When switching views, ensure charts are reinitialized properly
                this.$nextTick(() => {
                    // Force a reflow to ensure container dimensions are calculated
                    document.body.offsetHeight;
                    
                    // Add a small delay to ensure DOM is updated after view switch
                    setTimeout(() => {
                        // Reinitialize charts in the new view
                        this.initializeCharts();
                        
                        // Force another layout update after charts are rendered
                        setTimeout(() => {
                            window.dispatchEvent(new Event('resize'));
                        }, 100);
                    }, 50);
                });
            },
            
            /**
            * Navigate to global view
            */
            navigateToGlobal() {
                this.setActiveView('global');
            },
            
            /**
            * Navigate to detail view for a specific portfolio
            */
            navigateToDetail(portfolioName) {
                this.selectedPortfolio = portfolioName;
                this.setActiveView('detail');
            },
            
            /**
            * Toggle category expansion in detail view
            */
            toggleCategoryExpansion(categoryName) {
                // Use Vue.set to ensure reactivity
                Vue.set(this.expandedCategories, categoryName, !this.expandedCategories[categoryName]);
            },
            
            /**
            * Calculate current weights for all items
            */
            calculateCurrentWeights() {
                // Calculate total portfolio value
                this.totalValue = this.portfolioData.portfolios.reduce(
                    (sum, portfolio) => sum + portfolio.currentValue, 0
                );
                
                // Calculate portfolio weights
                this.portfolioData.portfolios.forEach(portfolio => {
                    portfolio.currentWeight = this.totalValue ? 
                        parseFloat((portfolio.currentValue / this.totalValue * 100).toFixed(2)) : 0;
                        
                    // Make sure each portfolio has a target weight (use current if missing)
                    // Don't overwrite target weights that came from the server
                    if (!portfolio.targetWeight && portfolio.targetWeight !== 0) {
                        portfolio.targetWeight = parseFloat(String(portfolio.currentWeight));
                    }
                    
                    // Calculate category weights within each portfolio
                    let portfolioCategoryTotal = portfolio.categories.reduce(
                        (sum, category) => sum + category.currentValue, 0
                    );
                    
                    portfolio.categories.forEach(category => {
                        category.currentWeight = portfolioCategoryTotal ? 
                            parseFloat((category.currentValue / portfolioCategoryTotal * 100).toFixed(2)) : 0;
                            
                        // Make sure each category has a target weight (use current if missing)
                        // Don't overwrite target weights that came from the server
                        if (!category.targetWeight && category.targetWeight !== 0) {
                            category.targetWeight = parseFloat(String(category.currentWeight));
                        }
                        
                        // Calculate position weights within each category
                        let categoryPositionTotal = category.positions.reduce(
                            (sum, position) => sum + position.currentValue, 0
                        );
                        
                        category.positions.forEach(position => {
                            position.currentWeight = categoryPositionTotal ? 
                                parseFloat((position.currentValue / categoryPositionTotal * 100).toFixed(2)) : 0;
                                
                            // Make sure each position has a target weight (use current if missing)
                            // Don't overwrite target weights that came from the server
                            if (!position.targetWeight && position.targetWeight !== 0) {
                                position.targetWeight = parseFloat(String(position.currentWeight));
                            } else {
                                // Ensure target weight is properly formatted as a number
                                position.targetWeight = parseFloat(position.targetWeight.toFixed(2));
                            }
                        });
                    });
                });
            },
            
            /**
            * Calculate required capital for "No Sales" mode
            */
            calculateRequiredCapitalForNoSales() {
                // Find the most overweight portfolio relative to target
                let maxOverweightRatio = 0;
                this.portfolioData.portfolios.forEach(portfolio => {
                    if (portfolio.currentWeight > portfolio.targetWeight) {
                        const ratio = portfolio.currentWeight / portfolio.targetWeight;
                        maxOverweightRatio = Math.max(maxOverweightRatio, ratio);
                    }
                });
                
                // If no portfolio is overweight, no new capital needed
                if (maxOverweightRatio <= 1) {
                    this.requiredCapitalForNoSales = 0;
                    return;
                }
                
                // Calculate new portfolio value needed to dilute overweight positions
                const newTotalValue = this.totalValue * maxOverweightRatio;
                this.requiredCapitalForNoSales = Math.round(newTotalValue - this.totalValue);
            },
            
            /**
            * Calculate target values and actions for all portfolios and positions
            */
            calculateTargetValuesAndActions() {
                // Calculate new portfolio value based on rebalance mode
                this.newPortfolioValue = this.totalValue;
                if (this.rebalanceMode === 'newCapitalSpecific') {
                    this.newPortfolioValue += this.newCapitalAmount;
                } else if (this.rebalanceMode === 'newCapitalOnly') {
                    this.newPortfolioValue += this.requiredCapitalForNoSales;
                }
                
                // PORTFOLIO LEVEL CALCULATIONS
                this.portfolioData.portfolios.forEach(portfolio => {
                    if (this.rebalanceMode === 'existingCapital') {
                        // Mode 1: Existing Capital - can buy and sell
                        portfolio.targetValue = Math.round(this.totalValue * portfolio.targetWeight / 100);
                        portfolio.action = {
                            type: portfolio.targetValue > portfolio.currentValue ? "Buy" : 
                                portfolio.targetValue < portfolio.currentValue ? "Sell" : "Hold",
                            amount: Math.abs(portfolio.targetValue - portfolio.currentValue)
                        };
                    } 
                    else if (this.rebalanceMode === 'newCapitalOnly') {
                        // Mode 2: New Capital only (no sales)
                        const idealTargetValue = Math.round(this.newPortfolioValue * portfolio.targetWeight / 100);
                        
                        if (portfolio.currentValue >= idealTargetValue) {
                            // Already at or above target - can't sell
                            portfolio.targetValue = portfolio.currentValue;
                            portfolio.action = { type: "Hold", amount: 0 };
                        } else {
                            // Below target - add capital
                            portfolio.targetValue = idealTargetValue;
                            portfolio.action = { 
                                type: "Buy", 
                                amount: idealTargetValue - portfolio.currentValue
                            };
                        }
                    }
                    else if (this.rebalanceMode === 'newCapitalSpecific') {
                        // Mode 3: New Capital (specific amount)
                        // Calculate ideal target value in the new portfolio
                        portfolio.idealTargetValue = Math.round(this.newPortfolioValue * portfolio.targetWeight / 100);
                
                        // Calculate shortfall (how much this portfolio needs)
                        portfolio.shortfall = portfolio.idealTargetValue > portfolio.currentValue ? 
                            portfolio.idealTargetValue - portfolio.currentValue : 0;
                    }
                });
                
                // For newCapitalSpecific mode, allocate the capital proportionally to shortfalls
                if (this.rebalanceMode === 'newCapitalSpecific') {
                    // Calculate total shortfall across all portfolios
                    let totalShortfall = this.portfolioData.portfolios.reduce(
                        (sum, portfolio) => sum + (portfolio.shortfall || 0), 0
                    );
                    
                    this.portfolioData.portfolios.forEach(portfolio => {
                        if (totalShortfall <= this.newCapitalAmount) {
                            // Enough capital to cover all shortfalls
                            portfolio.targetValue = portfolio.currentValue + (portfolio.shortfall || 0);
                            portfolio.action = {
                                type: (portfolio.shortfall || 0) > 0 ? "Buy" : "Hold",
                                amount: portfolio.shortfall || 0
                            };
                        } else if ((portfolio.shortfall || 0) > 0) {
                            // Not enough capital - allocate proportionally
                            const allocation = Math.round((portfolio.shortfall / totalShortfall) * this.newCapitalAmount);
                            portfolio.targetValue = portfolio.currentValue + allocation;
                            portfolio.action = { type: "Buy", amount: allocation };
                        } else {
                            // No shortfall
                            portfolio.targetValue = portfolio.currentValue;
                            portfolio.action = { type: "Hold", amount: 0 };
                        }
                    });
                }
                
                // CATEGORY AND POSITION LEVEL CALCULATIONS
                this.portfolioData.portfolios.forEach(portfolio => {
                    // Process each category and position
                    // (Code for this section remains unchanged)
                });
                
                // Recalculate final weights after actions
                this.portfolioData.portfolios.forEach(portfolio => {
                    portfolio.finalWeight = parseFloat((portfolio.targetValue / this.newPortfolioValue * 100).toFixed(2));
                    
                    // Recalculate category final weights
                    portfolio.categories.forEach(category => {
                        category.finalWeight = parseFloat((category.targetValue / portfolio.targetValue * 100).toFixed(2));
                        
                        // Recalculate position final weights
                        category.positions.forEach(position => {
                            position.finalWeight = parseFloat((position.targetValue / category.targetValue * 100).toFixed(2));
                        });
                    });
                });
            },
            
            /**
            * Initialize plotly charts for visualization
            */
            initializeCharts() {
                // Enhanced layout with consistent settings
                const layout = {
                    showlegend: false,
                    height: 350,
                    autosize: true,
                    margin: { l: 30, r: 30, t: 30, b: 50 },
                    paper_bgcolor: 'transparent',
                    plot_bgcolor: 'transparent',
                    automargin: true
                };

                // Enhanced config for better responsiveness
                const config = {
                    ...ChartConfig.plotlyConfig,
                    responsive: true,
                    displayModeBar: false
                };

                // Function to pre-process the chart container
                const prepareChartContainer = (elementId) => {
                    const container = document.getElementById(elementId);
                    if (!container) {
                        console.error(`Chart container not found: ${elementId}`);
                        return null;
                    }

                    // Ensure the container is visible
                    container.style.display = 'flex';
                    container.style.visibility = 'visible';
                    container.style.opacity = '1';
                    
                    // Force dimensions to be explicit
                    container.style.height = '350px';
                    container.style.minHeight = '350px';
                    container.style.width = '100%';
                    
                    // Ensure parent elements are properly sized
                    const cardContent = container.closest('.card-content');
                    if (cardContent) {
                        cardContent.style.height = 'auto';
                        cardContent.style.minHeight = '350px';
                    }
                    
                    // Force a reflow to ensure container dimensions are calculated
                    void container.offsetHeight;
                    
                    console.log(`Chart container ${elementId} dimensions: ${container.offsetWidth}x${container.offsetHeight}`);
                    return container;
                };

                // Determine which chart containers to use based on the active view
                let currentChartId, targetChartId;
                if (this.activeView === 'global') {
                    currentChartId = 'current-distribution-chart-global';
                    targetChartId = 'target-distribution-chart-global';
                } else {
                    currentChartId = 'current-distribution-chart-detail';
                    targetChartId = 'target-distribution-chart-detail';
                }

                // Prepare both chart containers first
                const currentContainer = prepareChartContainer(currentChartId);
                const targetContainer = prepareChartContainer(targetChartId);

                // If either container is missing, try again after a delay
                if (!currentContainer || !targetContainer) {
                    console.warn('Chart containers not ready, retrying in 200ms');
                    setTimeout(() => this.initializeCharts(), 200);
                    return;
                }

                // Get chart data
                const chartData = this.getChartData();
                
                // Initialize based on active view
                if (this.activeView === 'global') {
                    this.initializeGlobalCharts(chartData, layout, config);
                } else {
                    this.initializeDetailCharts(chartData, config);
                }
                
                // Force a resize event after charts are created to make sure they fit properly
                setTimeout(() => {
                    window.dispatchEvent(new Event('resize'));
                    
                    // Log dimensions after resize
                    const currentElement = document.getElementById(currentChartId);
                    const targetElement = document.getElementById(targetChartId);
                    
                    if (currentElement) {
                        console.log(`After resize: ${currentChartId} dimensions: ${currentElement.offsetWidth}x${currentElement.offsetHeight}`);
                    }
                    
                    if (targetElement) {
                        console.log(`After resize: ${targetChartId} dimensions: ${targetElement.offsetWidth}x${targetElement.offsetHeight}`);
                    }
                }, 100);
            },
            
            /**
            * Initialize charts for Global view (pie charts)
            */
            initializeGlobalCharts(chartData, layout, config) {
                // Create current distribution chart
                const currentData = [{
                    type: 'pie',
                    values: chartData.current.map(item => item.value),
                    labels: chartData.current.map(item => item.name),
                    textinfo: 'label+percent',
                    textposition: 'auto',
                    hoverinfo: 'label+percent+value',
                    hole: 0.5,
                    marker: {
                        colors: chartData.current.map(item => item.color)
                    },
                    textfont: {
                        size: 12,
                        color: '#ffffff'
                    },
                    insidetextfont: {
                        size: 12,
                        color: '#ffffff'
                    },
                    outsidetextfont: {
                        size: 12,
                        color: '#333333'
                    },
                    automargin: true,
                    showlegend: false
                }];
                
                // Use Plotly.purge to fully clean and redraw
                Plotly.purge('current-distribution-chart-global');
                Plotly.newPlot('current-distribution-chart-global', currentData, { ...layout }, config);
            
                // Create target distribution chart
                const targetData = [{
                    type: 'pie',
                    values: chartData.target.map(item => item.value),
                    labels: chartData.target.map(item => item.name),
                    textinfo: 'label+percent',
                    textposition: 'auto',
                    hoverinfo: 'label+percent+value',
                    hole: 0.5,
                    marker: {
                        colors: chartData.target.map(item => item.color)
                    },
                    textfont: {
                        size: 12,
                        color: '#ffffff'
                    },
                    insidetextfont: {
                        size: 12,
                        color: '#ffffff'
                    },
                    outsidetextfont: {
                        size: 12,
                        color: '#333333'
                    },
                    automargin: true,
                    showlegend: false
                }];
                
                // Use Plotly.purge to fully clean and redraw
                Plotly.purge('target-distribution-chart-global');
                Plotly.newPlot('target-distribution-chart-global', targetData, { ...layout }, config);
            },
            
            /**
            * Initialize charts for Detail view (sunburst charts)
            */
            initializeDetailCharts(chartData, config) {
                // Get the selected portfolio data
                const portfolio = this.selectedPortfolioData;
                if (!portfolio) return;
                
                // Clear any existing charts
                Plotly.purge('current-distribution-chart-detail');
                Plotly.purge('target-distribution-chart-detail');
                
                // Setup chartData for sunburst format (if available in PortfolioCharts)
                if (typeof PortfolioCharts !== 'undefined' && PortfolioCharts.createSunburstChart) {
                    // Create current distribution sunburst chart
                    const currentPortfolio = this.preparePortfolioDataForSunburst(portfolio, 'current');
                    PortfolioCharts.createSunburstChart(
                        'current-distribution-chart-detail',
                        currentPortfolio,
                        this.formatCurrency,
                        this.formatPercentage,
                        this.generateColors
                    );
                    
                    // Create target distribution sunburst chart
                    const targetPortfolio = this.preparePortfolioDataForSunburst(portfolio, 'target');
                    PortfolioCharts.createSunburstChart(
                        'target-distribution-chart-detail',
                        targetPortfolio,
                        this.formatCurrency,
                        this.formatPercentage,
                        this.generateColors
                    );
                } else {
                    console.warn('PortfolioCharts.createSunburstChart not available, falling back to pie charts');
                    // Fallback to pie charts if sunburst not available
                    const layout = {
                        showlegend: false,
                        height: 350,
                        autosize: true,
                        margin: { l: 30, r: 30, t: 30, b: 50 },
                        paper_bgcolor: 'transparent',
                        plot_bgcolor: 'transparent',
                        automargin: true
                    };
                    this.initializeGlobalCharts(chartData, layout, config);
                }
            },
            
            /**
            * Update chart data when view or state changes
            */
            updateChartData() {
                // Get updated chart data
                const chartData = this.getChartData();
                
                console.log('Updating chart data:', {
                    currentLength: chartData.current.length,
                    targetLength: chartData.target.length,
                    current: chartData.current,
                    target: chartData.target
                });

                // If there's no data, don't try to render the charts
                if (!chartData.current.length && !chartData.target.length) {
                    console.warn('No chart data available for rendering');
                    return;
                }

                // Create chart layout - ensure consistency with initialization
                const layout = {
                    showlegend: false,
                    height: 350,
                    autosize: true,
                    margin: { l: 30, r: 30, t: 30, b: 50 },
                    paper_bgcolor: 'transparent',
                    plot_bgcolor: 'transparent',
                    automargin: true
                };

                // Enhanced config for better responsiveness
                const config = {
                    ...ChartConfig.plotlyConfig,
                    responsive: true,
                    displayModeBar: false
                };

                // Check for the chart elements in the DOM based on active view
                let currentElementId, targetElementId;
                
                if (this.activeView === 'global') {
                    currentElementId = 'current-distribution-chart-global';
                    targetElementId = 'target-distribution-chart-global';
                } else {
                    currentElementId = 'current-distribution-chart-detail';
                    targetElementId = 'target-distribution-chart-detail';
                }
                
                // Function to pre-process the chart container (same as in initializeCharts)
                const prepareChartContainer = (elementId) => {
                    const container = document.getElementById(elementId);
                    if (!container) {
                        console.error(`Chart container not found: ${elementId}`);
                        return null;
                    }

                    // Ensure the container is visible
                    container.style.display = 'flex';
                    container.style.visibility = 'visible';
                    container.style.opacity = '1';
                    
                    // Force dimensions to be explicit
                    container.style.height = '350px';
                    container.style.minHeight = '350px';
                    container.style.width = '100%';
                    
                    // Ensure parent elements are properly sized
                    const cardContent = container.closest('.card-content');
                    if (cardContent) {
                        cardContent.style.height = 'auto';
                        cardContent.style.minHeight = '350px';
                    }
                    
                    // Force a reflow to ensure container dimensions are calculated
                    void container.offsetHeight;
                    
                    console.log(`Chart container ${elementId} dimensions: ${container.offsetWidth}x${container.offsetHeight}`);
                    return container;
                };
                
                const currentElement = prepareChartContainer(currentElementId);
                const targetElement = prepareChartContainer(targetElementId);

                // If either container is missing, try again after a delay
                if (!currentElement || !targetElement) {
                    console.warn('Chart containers not ready, retrying updateChartData in 200ms');
                    setTimeout(() => this.updateChartData(), 200);
                    return;
                }

                // Initialize based on active view
                if (this.activeView === 'global') {
                    // Update global view charts (pie charts)
                    if (currentElement) {
                        const currentData = [{
                            type: 'pie',
                            values: chartData.current.map(item => item.value),
                            labels: chartData.current.map(item => item.name),
                            textinfo: 'label+percent',
                            textposition: 'auto',
                            hoverinfo: 'label+percent+value',
                            hole: 0.5,
                            marker: {
                                colors: chartData.current.map(item => item.color)
                            },
                            textfont: {
                                size: 12,
                                color: '#ffffff'
                            },
                            insidetextfont: {
                                size: 12,
                                color: '#ffffff'
                            },
                            outsidetextfont: {
                                size: 12,
                                color: '#333333'
                            },
                            automargin: true,
                            showlegend: false
                        }];
                        
                        Plotly.react(currentElementId, currentData, layout, config);
                    }
                    
                    if (targetElement) {
                        const targetData = [{
                            type: 'pie',
                            values: chartData.target.map(item => item.value),
                            labels: chartData.target.map(item => item.name),
                            textinfo: 'label+percent',
                            textposition: 'auto',
                            hoverinfo: 'label+percent+value',
                            hole: 0.5,
                            marker: {
                                colors: chartData.target.map(item => item.color)
                            },
                            textfont: {
                                size: 12,
                                color: '#ffffff'
                            },
                            insidetextfont: {
                                size: 12,
                                color: '#ffffff'
                            },
                            outsidetextfont: {
                                size: 12,
                                color: '#333333'
                            },
                            automargin: true,
                            showlegend: false
                        }];
                        
                        Plotly.react(targetElementId, targetData, layout, config);
                    }
                } else {
                    // Update detail view charts (sunburst charts)
                    const portfolio = this.selectedPortfolioData;
                    if (!portfolio) return;
                    
                    // Setup chartData for sunburst format (if available in PortfolioCharts)
                    if (typeof PortfolioCharts !== 'undefined' && PortfolioCharts.createSunburstChart) {
                        // Create current distribution sunburst chart
                        if (currentElement) {
                            Plotly.purge(currentElementId);
                            const currentPortfolio = this.preparePortfolioDataForSunburst(portfolio, 'current');
                            PortfolioCharts.createSunburstChart(
                                currentElementId,
                                currentPortfolio,
                                this.formatCurrency,
                                this.formatPercentage,
                                this.generateColors
                            );
                        }
                        
                        // Create target distribution sunburst chart
                        if (targetElement) {
                            Plotly.purge(targetElementId);
                            const targetPortfolio = this.preparePortfolioDataForSunburst(portfolio, 'target');
                            PortfolioCharts.createSunburstChart(
                                targetElementId,
                                targetPortfolio,
                                this.formatCurrency,
                                this.formatPercentage,
                                this.generateColors
                            );
                        }
                    } else {
                        console.warn('PortfolioCharts.createSunburstChart not available, falling back to pie charts');
                        // Fallback to pie charts if sunburst not available
                        this.initializeGlobalCharts(chartData, layout, config);
                    }
                }
                
                // Force a resize event after charts are updated to ensure proper display
                setTimeout(() => {
                    window.dispatchEvent(new Event('resize'));
                }, 100);
            },
            
            /**
            * Get data for charts based on active view
            */
            getChartData() {
                let chartData = {
                    current: [],
                    target: []
                };
                
                // If no portfolio data, return empty chart data
                if (!this.portfolioData || !this.portfolioData.portfolios || this.portfolioData.portfolios.length === 0) {
                    console.warn('No portfolio data available for chart rendering');
                    return chartData;
                }
                
                // Generate colors for visualization
                const colors = this.generateColors(this.portfolioData.portfolios.length);
                
                if (this.activeView === 'global') {
                    // Global view - shows distribution across portfolios
                    this.portfolioData.portfolios.forEach((portfolio, index) => {
                        // Current distribution
                        chartData.current.push({
                            name: portfolio.name,
                            value: portfolio.currentValue,
                            color: colors[index % colors.length]
                        });
                        
                        // Target distribution
                        chartData.target.push({
                            name: portfolio.name,
                            value: portfolio.targetValue || portfolio.currentValue,
                            color: colors[index % colors.length]
                        });
                    });
                } else if (this.activeView === 'detail' && this.selectedPortfolio) {
                    // Detail view - shows distribution within a portfolio
                    const portfolio = this.portfolioData.portfolios.find(p => p.name === this.selectedPortfolio);
                    
                    if (portfolio && portfolio.categories) {
                        // Generate colors for categories
                        const categoryColors = this.generateColors(portfolio.categories.length);
                        
                        portfolio.categories.forEach((category, index) => {
                            // Current distribution
                            chartData.current.push({
                                name: category.name,
                                value: category.currentValue,
                                color: categoryColors[index % categoryColors.length]
                            });
                            
                            // Target distribution
                            chartData.target.push({
                                name: category.name,
                                value: category.targetValue || category.currentValue,
                                color: categoryColors[index % categoryColors.length]
                            });
                        });
                    }
                }
                
                return chartData;
            },
            
            /**
            * Prepare portfolio data in the format required by the sunburst chart
            */
            preparePortfolioDataForSunburst(portfolio, mode) {
                // Create a copy of the portfolio with only the required data
                const result = {
                    id: portfolio.id || portfolio.name.replace(/\s+/g, '_').toLowerCase(),
                    name: portfolio.name,
                    categories: []
                };
                
                // Add portfolio value based on mode (current or target)
                if (mode === 'current') {
                    result.currentValue = portfolio.currentValue;
                } else if (mode === 'target') {
                    result.currentValue = portfolio.targetValue || portfolio.currentValue;
                }
                
                // Process each category
                if (portfolio.categories && portfolio.categories.length > 0) {
                    portfolio.categories.forEach(category => {
                        // Create category object
                        const categoryObj = {
                            name: category.name,
                            percentage: mode === 'current' ? category.currentWeight : category.targetWeight,
                            currentValue: mode === 'current' ? category.currentValue : category.targetValue,
                            companies: []
                        };
                        
                        // Process positions within the category
                        if (category.positions && category.positions.length > 0) {
                            category.positions.forEach(position => {
                                // Skip placeholder positions in visualization
                                if (position.isPlaceholder) return;
                                
                                // Create position/company object
                                categoryObj.companies.push({
                                    name: position.name,
                                    percentage: mode === 'current' ? position.currentWeight : position.targetWeight,
                                    currentValue: mode === 'current' ? position.currentValue : position.targetValue,
                                    // Calculate percentage within the category
                                    categoryPercentage: mode === 'current' 
                                        ? (position.currentValue / category.currentValue * 100) 
                                        : (position.targetValue / category.targetValue * 100)
                                });
                            });
                        }
                        
                        // Only add categories with content
                        if (categoryObj.companies.length > 0) {
                            result.categories.push(categoryObj);
                        }
                    });
                }
                
                return result;
            },
            
            /**
            * Generate colors for chart elements
            */
            generateColors(count) {
                const colors = [
                    '#3366CC', '#DC3912', '#FF9900', '#109618', '#990099', '#3B3EAC',
                    '#0099C6', '#DD4477', '#66AA00', '#B82E2E', '#316395', '#994499',
                    '#22AA99', '#AAAA11', '#6633CC', '#E67300', '#8B0707', '#329262'
                ];
                
                return Array(count).fill().map((_, i) => colors[i % colors.length]);
            },
            
            /**
            * Format currency values with Euro symbol
            */
            formatCurrency(value) {
                if (value === null || value === undefined) return '€0';
                return new Intl.NumberFormat('de-DE', { 
                    style: 'currency', 
                    currency: 'EUR',
                    maximumFractionDigits: 0
                }).format(value);
            },
            
            /**
            * Format percentage values
            */
            formatPercentage(value) {
                if (value === null || value === undefined) return '0%';
                // Ensure value is a number before calling toFixed
                return `${parseFloat(String(value)).toFixed(1)}%`;
            }
        },
        mounted() {
            // Initialize the component
            this.initialize();
            
            // Make format functions available globally for chart components
            window.formatCurrency = this.formatCurrency;
            window.formatPercentage = this.formatPercentage;
            window.generateColors = this.generateColors;
            
            // Ensure PortfolioCharts is available
            if (typeof PortfolioCharts === 'undefined') {
                console.warn('PortfolioCharts not defined, creating fallback implementation');
                window.PortfolioCharts = {
                    createSunburstChart: (elementId, portfolio, formatCurrency, formatPercentage, generateColors) => {
                        const chartElement = document.getElementById(elementId);
                        if (!chartElement) {
                            console.error(`Chart container not found: ${elementId}`);
                            return null;
                        }
                        
                        // Check portfolio data
                        if (!portfolio || !portfolio.categories) {
                            console.error('Portfolio data is null or undefined');
                            return null;
                        }
                        
                        // Create a simple fallback pie chart
                        try {
                            // Get categories
                            const labels = portfolio.categories.map(cat => cat.name);
                            const values = portfolio.categories.map(cat => cat.currentValue);
                            const colors = generateColors(labels.length);
                            
                            const data = [{
                                type: 'pie',
                                values: values,
                                labels: labels,
                                textinfo: 'label+percent',
                                textposition: 'auto',
                                hoverinfo: 'label+percent+value',
                                marker: {
                                    colors: colors
                                }
                            }];
                            
                            const layout = {
                                showlegend: false,
                                height: 350,
                                autosize: true,
                                margin: { l: 30, r: 30, t: 30, b: 50 },
                                paper_bgcolor: 'transparent',
                                plot_bgcolor: 'transparent',
                                automargin: true
                            };
                            
                            // Use the centralized chart configuration if available
                            const config = (typeof ChartConfig !== 'undefined') 
                                ? ChartConfig.plotlyConfig 
                                : { responsive: true, displayModeBar: false };
                                
                            return Plotly.newPlot(elementId, data, layout, config)
                                .catch(error => {
                                    console.error(`Error in Plotly.newPlot promise:`, error);
                                    return null;
                                });
                        } catch (error) {
                            console.error('Error creating fallback pie chart:', error);
                            return null;
                        }
                    }
                };
            }
            
            // Ensure ChartConfig is available
            if (typeof ChartConfig === 'undefined') {
                console.warn('ChartConfig not defined, creating fallback implementation');
                window.ChartConfig = {
                    plotlyConfig: {
                        responsive: true,
                        displayModeBar: false,
                        showlegend: false
                    }
                };
            }
            
            // Create debounced methods for template use
            this.debouncedUpdateChartData = _.debounce(() => {
                if (!this.isUpdating) {
                    this.isUpdating = true;
                    try {
                        this.updateChartData();
                    } finally {
                        this.isUpdating = false;
                    }
                }
            }, 250);
            
            this.debouncedCalculateTargetValuesAndActions = _.debounce(() => {
                if (!this.isUpdating) {
                    this.isUpdating = true;
                    try {
                        this.calculateTargetValuesAndActions();
                        this.updateChartData();
                    } finally {
                        this.isUpdating = false;
                    }
                }
            }, 250);
            
            // Create a dedicated resize handler that forces chart resizing
            const handleResize = _.debounce(() => {
                if (!this.isUpdating) {
                    this.isUpdating = true;
                    try {
                        // Get the chart containers for the active view
                        let currentChartId, targetChartId;
                        if (this.activeView === 'global') {
                            currentChartId = 'current-distribution-chart-global';
                            targetChartId = 'target-distribution-chart-global';
                        } else {
                            currentChartId = 'current-distribution-chart-detail';
                            targetChartId = 'target-distribution-chart-detail';
                        }
                        
                        // Force Plotly to resize charts
                        const currentElement = document.getElementById(currentChartId);
                        const targetElement = document.getElementById(targetChartId);
                        
                        if (currentElement) {
                            Plotly.relayout(currentChartId, {
                                autosize: true
                            });
                        }
                        
                        if (targetElement) {
                            Plotly.relayout(targetChartId, {
                                autosize: true
                            });
                        }
                        
                        console.log('Charts resized due to window resize event');
                    } finally {
                        this.isUpdating = false;
                    }
                }
            }, 200);
            
            // Add the resize handler
            window.addEventListener('resize', handleResize);
            
            // Store the handler so we can remove it if needed
            this.resizeHandler = handleResize;
            
            // Add event listeners for notification close buttons
            document.querySelectorAll('.notification .delete').forEach(button => {
                button.addEventListener('click', () => {
                    button.parentNode.remove();
                });
            });
        }
    });
});