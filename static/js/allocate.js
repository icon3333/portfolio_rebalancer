/**
 * Portfolio Rebalancer - Vue.js Component
 * 
 * This component provides portfolio rebalancing functionality including:
 * - Visualizing current vs target allocation
 * - Multiple rebalancing modes
 * - Detailed breakdown of required actions
 */

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

document.addEventListener('DOMContentLoaded', function() {
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
                        {
                            name: "Value",
                            currentValue: 42000,
                            targetWeight: 35,
                            color: "#003366",
                            categories: [
                                {
                                    name: "US Equities",
                                    currentValue: 25000,
                                    targetWeight: 55,
                                    color: "#1F497D",
                                    positions: [
                                        { name: "VTI", currentValue: 15000, targetWeight: 65, color: "#4472C4" },
                                        { name: "VOO", currentValue: 10000, targetWeight: 35, color: "#5B9BD5" }
                                    ]
                                },
                                {
                                    name: "International",
                                    currentValue: 17000,
                                    targetWeight: 45,
                                    color: "#2E75B6",
                                    positions: [
                                        { name: "VXUS", currentValue: 10000, targetWeight: 60, color: "#70AD47" },
                                        { name: "EFA", currentValue: 7000, targetWeight: 40, color: "#9DC3E6" }
                                    ]
                                }
                            ]
                        },
                        {
                            name: "Dividend",
                            currentValue: 33000,
                            targetWeight: 40,
                            color: "#673AB7",
                            categories: [
                                {
                                    name: "High Yield",
                                    currentValue: 20000,
                                    targetWeight: 65,
                                    color: "#7E57C2",
                                    positions: [
                                        { name: "SCHD", currentValue: 12000, targetWeight: 55, color: "#9575CD" },
                                        { name: "VYM", currentValue: 8000, targetWeight: 45, color: "#B39DDB" }
                                    ]
                                },
                                {
                                    name: "REITs",
                                    currentValue: 13000,
                                    targetWeight: 35,
                                    color: "#9C27B0",
                                    positions: [
                                        { name: "VNQ", currentValue: 8000, targetWeight: 60, color: "#CE93D8" },
                                        { name: "STAG", currentValue: 5000, targetWeight: 40, color: "#E1BEE7" }
                                    ]
                                }
                            ]
                        },
                        {
                            name: "Crypto",
                            currentValue: 25000,
                            targetWeight: 25,
                            color: "#1F497D",
                            categories: [
                                {
                                    name: "Large Cap",
                                    currentValue: 20000,
                                    targetWeight: 75,
                                    color: "#31859C",
                                    positions: [
                                        { name: "BTC", currentValue: 12000, targetWeight: 60, color: "#4BACC6" },
                                        { name: "ETH", currentValue: 8000, targetWeight: 40, color: "#92CDDC" }
                                    ]
                                },
                                {
                                    name: "Alt Coins",
                                    currentValue: 5000,
                                    targetWeight: 25,
                                    color: "#76A5AF",
                                    positions: [
                                        { name: "SOL", currentValue: 3000, targetWeight: 50, color: "#A5A5A5" },
                                        { name: "ADA", currentValue: 2000, targetWeight: 50, color: "#D9D9D9" }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                
                // Calculated values
                totalValue: 0,
                newPortfolioValue: 0,
                requiredCapitalForNoSales: 0,
                
                // Loading state
                isLoading: false
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
                this.calculateTargetValuesAndActions();
                this.updateChartData();
            },
            
            /**
             * Watch for changes to new capital amount and recalculate
             */
            newCapitalAmount() {
                if (this.rebalanceMode === 'newCapitalSpecific') {
                    this.calculateTargetValuesAndActions();
                    this.updateChartData();
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
                            
                            // If we received no portfolios or they have no data, fall back to mock data
                            if (this.portfolioData.portfolios.length === 0) {
                                console.warn('No portfolio data found, using mock data for demo purposes');
                                this.portfolioData = JSON.parse(JSON.stringify(this.mockData));
                            }
                            
                            // Calculate initial values
                            this.calculateCurrentWeights();
                            this.calculateRequiredCapitalForNoSales();
                            this.calculateTargetValuesAndActions();
                            
                            // Set default selected portfolio
                            if (this.portfolioData.portfolios.length > 0 && !this.selectedPortfolio) {
                                this.selectedPortfolio = this.portfolioData.portfolios[0].name;
                            }
                            
                            // Initialize charts
                            this.$nextTick(() => {
                                this.initializeCharts();
                            });
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
                        
                        // Calculate initial values
                        this.calculateCurrentWeights();
                        this.calculateRequiredCapitalForNoSales();
                        this.calculateTargetValuesAndActions();
                        
                        // Initialize charts
                        this.$nextTick(() => {
                            this.initializeCharts();
                        });
                    })
                    .finally(() => {
                        this.isLoading = false;
                    });
            },
            
            /**
             * Set the active view (global or detail)
             */
            setActiveView(view) {
                if (this.activeView !== view) {
                    this.activeView = view;
                    
                    // Set default portfolio if needed when switching to detail view
                    if (view === 'detail' && !this.selectedPortfolio && this.portfolioData.portfolios.length > 0) {
                        this.selectedPortfolio = this.portfolioData.portfolios[0].name;
                    }
                    
                    // Wait for DOM update before updating charts
                    this.$nextTick(() => {
                        // Force a complete redraw of the charts
                        Plotly.purge('current-distribution-chart');
                        Plotly.purge('target-distribution-chart');
                        this.updateChartData();
                        
                        // Resize charts to ensure they fit the container
                        setTimeout(() => {
                            window.dispatchEvent(new Event('resize'));
                        }, 100);
                    });
                }
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
                    if (!portfolio.targetWeight || isNaN(parseFloat(String(portfolio.targetWeight)))) {
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
                        if (!category.targetWeight || isNaN(parseFloat(String(category.targetWeight)))) {
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
                            if (!position.targetWeight || isNaN(parseFloat(String(position.targetWeight)))) {
                                position.targetWeight = parseFloat(String(position.currentWeight));
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
                    // Calculate target values for categories
                    portfolio.categories.forEach(category => {
                        // Calculate category target value based on portfolio target
                        category.targetValue = Math.round(portfolio.targetValue * category.targetWeight / 100);
                        
                        // For existing capital mode, we can buy and sell within categories
                        if (this.rebalanceMode === 'existingCapital') {
                            category.action = {
                                type: category.targetValue > category.currentValue ? "Buy" : 
                                    category.targetValue < category.currentValue ? "Sell" : "Hold",
                                amount: Math.abs(category.targetValue - category.currentValue)
                            };
                        } 
                        // For new capital modes, we trickle down any "Buy" actions
                        else {
                            if (portfolio.action.type === "Buy") {
                                // Allocate new capital to categories based on their target weights
                                category.action = {
                                    type: "Buy",
                                    amount: Math.round(portfolio.action.amount * category.targetWeight / 100)
                                };
                                category.targetValue = category.currentValue + category.action.amount;
                            } else {
                                // No new capital for this portfolio
                                category.action = { type: "Hold", amount: 0 };
                                category.targetValue = category.currentValue;
                            }
                        }
                        
                        // POSITION LEVEL CALCULATIONS
                        category.positions.forEach(position => {
                            // Calculate position target value based on category target
                            position.targetValue = Math.round(category.targetValue * position.targetWeight / 100);
                            
                            // For existing capital mode, we can buy and sell within positions
                            if (this.rebalanceMode === 'existingCapital') {
                                position.action = {
                                    type: position.targetValue > position.currentValue ? "Buy" : 
                                        position.targetValue < position.currentValue ? "Sell" : "Hold",
                                    amount: Math.abs(position.targetValue - position.currentValue)
                                };
                            }
                            // For new capital modes, we trickle down any "Buy" actions
                            else {
                                if (category.action.type === "Buy") {
                                    // Allocate new capital to positions based on their target weights
                                    position.action = {
                                        type: "Buy",
                                        amount: Math.round(category.action.amount * position.targetWeight / 100)
                                    };
                                    position.targetValue = position.currentValue + position.action.amount;
                                } else {
                                    // No new capital for this category
                                    position.action = { type: "Hold", amount: 0 };
                                    position.targetValue = position.currentValue;
                                }
                            }
                        });
                    });
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
                // Enhanced layout with automargin
                const layout = {
                    showlegend: true,
                    legend: { 
                        orientation: 'h', 
                        y: -0.15,
                        xanchor: 'center',
                        x: 0.5,
                        font: { size: 12 }
                    },
                    height: 350,
                    autosize: true,
                    margin: { l: 30, r: 30, t: 30, b: 50 },
                    paper_bgcolor: 'transparent',
                    plot_bgcolor: 'transparent',
                    automargin: true
                };
            
                const chartData = this.getChartData();
                
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
                    automargin: true
                }];
                
                Plotly.newPlot('current-distribution-chart', currentData, { ...layout });
            
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
                    automargin: true
                }];
                
                Plotly.newPlot('target-distribution-chart', targetData, { ...layout });
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
                    showlegend: true,
                    legend: {
                        orientation: 'h',
                        y: -0.15,
                        xanchor: 'center',
                        x: 0.5,
                        font: { size: 12 }
                    },
                    height: 350,
                    autosize: true,
                    margin: { l: 30, r: 30, t: 30, b: 50 },
                    paper_bgcolor: 'transparent',
                    plot_bgcolor: 'transparent',
                    automargin: true
                };

                // Check for the chart elements in the DOM
                const currentElement = document.getElementById('current-distribution-chart');
                const targetElement = document.getElementById('target-distribution-chart');

                // Update current distribution chart if element exists and we have data
                if (currentElement && chartData.current.length > 0) {
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
                        automargin: true
                    }];
                    
                    // Use Plotly.purge to fully clean and redraw
                    Plotly.purge('current-distribution-chart');
                    Plotly.newPlot('current-distribution-chart', currentData, { ...layout });
                    console.log('Updated current distribution chart');
                }

                // Update target distribution chart if element exists and we have data
                if (targetElement && chartData.target.length > 0) {
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
                        automargin: true
                    }];
                    
                    // Use Plotly.purge to fully clean and redraw
                    Plotly.purge('target-distribution-chart');
                    Plotly.newPlot('target-distribution-chart', targetData, { ...layout });
                    console.log('Updated target distribution chart');
                } else {
                    // If we have target data but no element or couldn't plot, log a warning
                    if (chartData.target.length > 0) {
                        console.warn('Target chart element not found or unable to render target chart', 
                            targetElement ? 'Element exists' : 'Element not found');
                    }
                }
            },
            
            /**
             * Get data for charts based on active view
             */
            getChartData() {
                if (this.activeView === 'global') {
                    // Ensure all portfolios have valid target weights
                    const portfoliosWithTargets = this.portfolioData.portfolios.map(item => {
                        // Ensure target weight exists
                        if (!item.targetWeight && item.targetWeight !== 0) {
                            item.targetWeight = parseFloat(item.currentWeight || 0);
                        }
                        return item;
                    });
                    
                    // Filter out any items with zero values to prevent empty charts
                    const currentItems = portfoliosWithTargets.filter(item => 
                        item.currentWeight && parseFloat(String(item.currentWeight)) > 0
                    ).map(item => ({
                        name: item.name,
                        value: parseFloat(String(item.currentWeight || 0)),
                        color: item.color
                    }));
                    
                    const targetItems = portfoliosWithTargets.filter(item => {
                        // Use finalWeight, targetWeight, or currentWeight (in that order)
                        const value = parseFloat(
                            String(item.finalWeight || item.targetWeight || item.currentWeight || 0)
                        );
                        return value > 0;
                    }).map(item => ({
                        name: item.name,
                        value: parseFloat(
                            String(item.finalWeight || item.targetWeight || item.currentWeight || 0)
                        ),
                        color: item.color
                    }));
                    
                    console.log('Global View Chart Data:', {
                        current: currentItems,
                        target: targetItems,
                        portfolios: portfoliosWithTargets.map(p => ({
                            name: p.name,
                            currentWeight: p.currentWeight,
                            targetWeight: p.targetWeight,
                            finalWeight: p.finalWeight
                        }))
                    });
                    
                    // Fallback: if no data exists, supply dummy data so a blank chart is still rendered
                    if (currentItems.length === 0) {
                        currentItems.push({
                            name: 'No Data',
                            value: 100,
                            color: '#CCCCCC'
                        });
                    }
                    if (targetItems.length === 0) {
                        targetItems.push({
                            name: 'No Data',
                            value: 100,
                            color: '#CCCCCC'
                        });
                    }
                    
                    return {
                        current: currentItems,
                        target: targetItems
                    };
                } else if (this.activeView === 'detail' && this.selectedPortfolio) {
                    const portfolio = this.portfolioData.portfolios.find(p => p.name === this.selectedPortfolio);
                    if (!portfolio || !portfolio.categories) return { current: [], target: [] };
                    
                    // Ensure all categories have valid target weights
                    const categoriesWithTargets = portfolio.categories.map(item => {
                        // Ensure target weight exists
                        if (!item.targetWeight && item.targetWeight !== 0) {
                            item.targetWeight = parseFloat(item.currentWeight || 0);
                        }
                        return item;
                    });
                    
                    // Filter out any categories with zero values to prevent empty charts
                    const currentItems = categoriesWithTargets.filter(item => 
                        item.currentWeight && parseFloat(String(item.currentWeight)) > 0
                    ).map(item => ({
                        name: item.name,
                        value: parseFloat(String(item.currentWeight || 0)),
                        color: item.color
                    }));
                    
                    const targetItems = categoriesWithTargets.filter(item => {
                        // Use finalWeight, targetWeight, or currentWeight (in that order)
                        const value = parseFloat(
                            (item.finalWeight || item.targetWeight || item.currentWeight || 0).toString()
                        );
                        return value > 0;
                    }).map(item => ({
                        name: item.name,
                        value: parseFloat(
                            (item.finalWeight || item.targetWeight || item.currentWeight || 0).toString()
                        ),
                        color: item.color
                    }));
                    
                    console.log('Detail View Chart Data:', {
                        current: currentItems,
                        target: targetItems,
                        categories: categoriesWithTargets.map(c => ({
                            name: c.name,
                            currentWeight: c.currentWeight,
                            targetWeight: c.targetWeight,
                            finalWeight: c.finalWeight
                        }))
                    });
                    
                    // Fallback: if no data exists, supply dummy data so a blank chart is still rendered
                    if (currentItems.length === 0) {
                        currentItems.push({
                            name: 'No Data',
                            value: 100,
                            color: '#CCCCCC'
                        });
                    }
                    if (targetItems.length === 0) {
                        targetItems.push({
                            name: 'No Data',
                            value: 100,
                            color: '#CCCCCC'
                        });
                    }
                    
                    return {
                        current: currentItems,
                        target: targetItems
                    };
                }
                
                return { current: [], target: [] };
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
        // In mounted hook:
        mounted() {
            // Initialize the component
            this.initialize();
            
            // Ensure charts are properly rendered when data changes
            this.$watch('portfolioData', () => {
                this.$nextTick(() => {
                    // First calculate weights and actions
                    this.calculateCurrentWeights();
                    this.calculateRequiredCapitalForNoSales();
                    this.calculateTargetValuesAndActions();
                    
                    // Then update charts
                    this.updateChartData();
                });
            }, { deep: true });
            
            // Update charts when view changes
            this.$watch('activeView', () => {
                this.$nextTick(() => {
                    this.updateChartData();
                    
                    // Resize charts to ensure they fit the container
                    setTimeout(() => {
                        window.dispatchEvent(new Event('resize'));
                    }, 100);
                });
            });
            
            // Update charts when selected portfolio changes
            this.$watch('selectedPortfolio', () => {
                this.$nextTick(() => {
                    this.updateChartData();
                });
            });
            
            // Update charts when rebalance mode changes
            this.$watch('rebalanceMode', () => {
                this.$nextTick(() => {
                    this.calculateTargetValuesAndActions();
                    this.updateChartData();
                });
            });
            
            // Update charts when new capital amount changes
            this.$watch('newCapitalAmount', () => {
                this.$nextTick(() => {
                    this.calculateTargetValuesAndActions();
                    this.updateChartData();
                });
            });
            
            // Add window resize handler to ensure charts are responsive
            window.addEventListener('resize', () => {
                this.$nextTick(() => {
                    this.updateChartData();
                });
            });
            
            // Force an update after a short delay to ensure DOM is ready
            setTimeout(() => {
                this.updateChartData();
            }, 500);
        }
    });
});

/**
 * In a real implementation, we would include an API integration
 * For example:
 
// API Service
const PortfolioAPI = {
    async getPortfolioData() {
        try {
            const response = await fetch('/portfolio/api/rebalance_data');
            if (!response.ok) {
                throw new Error(`HTTP error ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            console.error('Error fetching portfolio data:', error);
            throw error;
        }
    }
};
 
 */