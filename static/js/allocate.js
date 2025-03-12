// Improved Portfolio Rebalancer JavaScript

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

    // Debounce function to prevent excessive updates
    function debounce(func, wait = 300) {
        let timeout;
        return function(...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
        };
    }

    // Create Vue application
    new Vue({
        el: '#portfolio-rebalancer',
        delimiters: ['${', '}'],  // Match existing Vue delimiters
        data() {
            return {
                // Selected portfolio
                selectedPortfolio: '',
                expandedCategories: {},
                
                // Chart instances
                currentChart: null,
                targetChart: null,
                
                // Calculated portfolio data
                portfolioData: {
                    portfolios: []
                },
                
                // Calculated values
                totalValue: 0,
                newPortfolioValue: 0,
                
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
                
                // Fetch data from our API endpoint
                axios.get('/portfolio/api/allocate/portfolio-data')
                    .then(response => {
                        if (response.data && response.data.portfolios) {
                            this.portfolioData = response.data;
                            console.log('Portfolio data loaded:', this.portfolioData);
                            
                            this.isUpdating = true;
                            try {
                                // Calculate initial values
                                this.calculateCurrentWeights();
                                this.calculateTargetValuesAndActions();
                                
                                // Initialize charts
                                this.$nextTick(() => {
                                    this.initializeCharts();
                                });
                            } finally {
                                this.isUpdating = false;
                            }
                        }
                    })
                    .catch(error => {
                        console.error('Error fetching portfolio data:', error);
                        // Show error notification
                        if (typeof portfolioManager !== 'undefined' && portfolioManager.showNotification) {
                            portfolioManager.showNotification('Failed to load portfolio data', 'is-danger');
                        }
                    })
                    .finally(() => {
                        this.isLoading = false;
                    });
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
             * Calculate target values and actions for all portfolios and positions
             */
            calculateTargetValuesAndActions() {
                // Set new portfolio value equal to current value (no new capital in this version)
                this.newPortfolioValue = this.totalValue;
                
                // PORTFOLIO LEVEL CALCULATIONS
                this.portfolioData.portfolios.forEach(portfolio => {
                    // Calculate target value based on weight
                    portfolio.targetValue = Math.round(this.totalValue * portfolio.targetWeight / 100);
                    
                    // Determine action (buy, sell, or hold)
                    portfolio.action = {
                        type: portfolio.targetValue > portfolio.currentValue ? "Buy" : 
                              portfolio.targetValue < portfolio.currentValue ? "Sell" : "Hold",
                        amount: Math.abs(portfolio.targetValue - portfolio.currentValue)
                    };
                    
                    // CATEGORY AND POSITION LEVEL CALCULATIONS
                    portfolio.categories.forEach(category => {
                        // Calculate target value for category based on portfolio's target value
                        category.targetValue = Math.round(portfolio.targetValue * category.targetWeight / 100);
                        
                        // Determine action for category
                        category.action = {
                            type: category.targetValue > category.currentValue ? "Buy" : 
                                  category.targetValue < category.currentValue ? "Sell" : "Hold",
                            amount: Math.abs(category.targetValue - category.currentValue)
                        };
                        
                        // Calculate target values and actions for positions
                        category.positions.forEach(position => {
                            // Calculate target value for position based on category's target value
                            position.targetValue = Math.round(category.targetValue * position.targetWeight / 100);
                            
                            // Determine action for position
                            position.action = {
                                type: position.targetValue > position.currentValue ? "Buy" : 
                                      position.targetValue < position.currentValue ? "Sell" : "Hold",
                                amount: Math.abs(position.targetValue - position.currentValue)
                            };
                        });
                    });
                    
                    // Recalculate final weights
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
             * Initialize charts for visualization
             */
            initializeCharts() {
                this.updateChartData();
            },
            
            /**
             * Update chart data when view or state changes
             */
            updateChartData() {
                // Get updated chart data
                const chartData = this.getChartData();
                
                // Clear previous charts
                Plotly.purge('current-distribution-chart');
                Plotly.purge('target-distribution-chart');
                
                // Determine which data to display based on selectedPortfolio
                if (this.selectedPortfolio) {
                    // Detail view - use sunburst chart for selected portfolio
                    const portfolio = this.selectedPortfolioData;
                    if (!portfolio) return;
                    
                    // Prepare data for sunburst charts
                    const currentPortfolio = this.preparePortfolioDataForSunburst(portfolio, 'current');
                    const targetPortfolio = this.preparePortfolioDataForSunburst(portfolio, 'target');
                    
                    // Create sunburst charts using PortfolioCharts if available
                    if (typeof PortfolioCharts !== 'undefined' && PortfolioCharts.createSunburstChart) {
                        PortfolioCharts.createSunburstChart(
                            'current-distribution-chart',
                            currentPortfolio,
                            this.formatCurrency,
                            this.formatPercentage,
                            this.generateColors
                        );
                        
                        PortfolioCharts.createSunburstChart(
                            'target-distribution-chart',
                            targetPortfolio,
                            this.formatCurrency,
                            this.formatPercentage,
                            this.generateColors
                        );
                    } else {
                        // Fallback to pie charts if sunburst not available
                        this.createPieCharts(chartData);
                    }
                } else {
                    // Global view - use pie charts
                    this.createPieCharts(chartData);
                }
            },
            
            /**
             * Create pie charts for current and target distribution
             */
            createPieCharts(chartData) {
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
                
                Plotly.newPlot('current-distribution-chart', currentData, layout, 
                    typeof ChartConfig !== 'undefined' ? ChartConfig.plotlyConfig : { displayModeBar: false });
            
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
                
                Plotly.newPlot('target-distribution-chart', targetData, layout,
                    typeof ChartConfig !== 'undefined' ? ChartConfig.plotlyConfig : { displayModeBar: false });
            },
            
            /**
             * Get data for charts based on selected portfolio
             */
            getChartData() {
                const colors = this.generateColors(this.portfolioData.portfolios.length);
                let currentData = [];
                let targetData = [];
                
                if (this.selectedPortfolio) {
                    // Selected portfolio mode - show categories
                    const portfolio = this.selectedPortfolioData;
                    if (portfolio) {
                        // Map colors to portfolio and categories
                        portfolio.color = colors[0]; // Use first color for portfolio
                        
                        // Create chart data for categories
                        const categoryColors = this.generateColors(portfolio.categories.length);
                        
                        portfolio.categories.forEach((category, index) => {
                            category.color = categoryColors[index];
                            
                            currentData.push({
                                name: category.name,
                                value: category.currentValue,
                                weight: category.currentWeight,
                                color: category.color
                            });
                            
                            targetData.push({
                                name: category.name,
                                value: category.targetValue,
                                weight: category.targetWeight,
                                color: category.color
                            });
                        });
                    }
                } else {
                    // Global mode - show all portfolios
                    this.portfolioData.portfolios.forEach((portfolio, index) => {
                        portfolio.color = colors[index % colors.length];
                        
                        currentData.push({
                            name: portfolio.name,
                            value: portfolio.currentValue,
                            weight: portfolio.currentWeight,
                            color: portfolio.color
                        });
                        
                        targetData.push({
                            name: portfolio.name,
                            value: portfolio.targetValue,
                            weight: portfolio.targetWeight,
                            color: portfolio.color
                        });
                    });
                }
                
                return {
                    current: currentData,
                    target: targetData
                };
            },
            
            /**
             * Prepare portfolio data in the format required by the sunburst chart
             */
            preparePortfolioDataForSunburst(portfolio, mode) {
                // Create a deep structure with portfolio at root, categories as children, and positions as leaf nodes
                const valueField = mode === 'current' ? 'currentValue' : 'targetValue';
                const weightField = mode === 'current' ? 'currentWeight' : 'targetWeight';
                
                const result = {
                    name: portfolio.name,
                    value: portfolio[valueField],
                    weight: portfolio[weightField],
                    children: []
                };
                
                // Add categories as children
                portfolio.categories.forEach(category => {
                    const categoryNode = {
                        name: category.name,
                        value: category[valueField],
                        weight: category[weightField],
                        children: []
                    };
                    
                    // Add positions as children of categories
                    category.positions.forEach(position => {
                        // Skip placeholder positions for cleaner visualization
                        if (position.isPlaceholder) return;
                        
                        categoryNode.children.push({
                            name: position.name,
                            value: position[valueField],
                            weight: position[weightField]
                        });
                    });
                    
                    // Only add categories that have positions
                    if (categoryNode.children.length > 0) {
                        result.children.push(categoryNode);
                    }
                });
                
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
        created() {
            // Create debounced methods
            this.debouncedUpdateChartData = debounce(this.updateChartData, 250);
        },
        mounted() {
            // Initialize the component
            this.initialize();
            
            // Make format functions available globally for chart components
            window.formatCurrency = this.formatCurrency;
            window.formatPercentage = this.formatPercentage;
            window.generateColors = this.generateColors;
            
            // Add the debounced resize handler
            const debouncedResize = debounce(() => {
                if (!this.isUpdating) {
                    this.isUpdating = true;
                    try {
                        this.updateChartData();
                    } finally {
                        this.isUpdating = false;
                    }
                }
            }, 250);
            
            window.addEventListener('resize', debouncedResize);
        }
    });
});