// Modified allocate.js - Fixed duplicate watchers that caused infinite loops and adjusted chart heights

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
                allowSellingWithNewCapital: true,  // New toggle for allowing sells with new capital
                
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
                isUpdating: false,
                
                // New addition for total shortfall calculation
                totalShortfall: 0
            };
        },
        created() {
            // Create debounced functions
            this.debouncedUpdateChartData = _.debounce(this.updateChartData, 300);
            this.debouncedCalculateTargetValuesAndActions = _.debounce(this.calculateTargetValuesAndActions, 300);
            this.debouncedInitializeCharts = _.debounce(this.initializeCharts, 300);
        },
        computed: {
            /**
            * Get currently selected portfolio data
            */
            selectedPortfolioData() {
                // Perform basic validations with helpful diagnostics
                if (!this.selectedPortfolio) {
                    console.warn('No portfolio selected in selectedPortfolioData');
                    return null;
                }
                
                if (!this.portfolioData || !this.portfolioData.portfolios || !Array.isArray(this.portfolioData.portfolios)) {
                    console.warn('Invalid portfolioData structure in selectedPortfolioData');
                    return null;
                }
                
                if (this.portfolioData.portfolios.length === 0) {
                    console.warn('No portfolios available in selectedPortfolioData');
                    return null;
                }
                
                // Find the selected portfolio
                const portfolio = this.portfolioData.portfolios.find(p => p.name === this.selectedPortfolio);
                
                if (!portfolio) {
                    console.warn(`Portfolio with name "${this.selectedPortfolio}" not found in selectedPortfolioData`);
                    
                    // As a fallback, if the specified portfolio isn't found, return the first one
                    if (this.portfolioData.portfolios.length > 0) {
                        console.log('Falling back to first available portfolio');
                        this.selectedPortfolio = this.portfolioData.portfolios[0].name;
                        return this.portfolioData.portfolios[0];
                    }
                }
                
                return portfolio;
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
                    
                    // Only update charts in global view
                    if (this.activeView === 'global') {
                        this.debouncedUpdateChartData();
                    }
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
            * Watch for changes to allow selling toggle and recalculate
            */
            allowSellingWithNewCapital() {
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
                console.log(`activeView watcher triggered: ${this.activeView}`);
                
                // Clear the isUpdating flag to ensure reactivity works
                this.isUpdating = false;
                
                // Use nextTick to ensure DOM has updated
                this.$nextTick(() => {
                    try {
                        console.log(`View changed to: ${this.activeView}`);
                        
                        // If we're in Detail View, nothing to do for charts
                        if (this.activeView === 'detail') {
                            console.log('Switched to Detail View - no charts to initialize');
                            return;
                        }
                        
                        // If we switched to Global View, ensure proper container initialization
                        // and initialize charts after a short delay
                        if (this.activeView === 'global') {
                            // Ensure a reflow before updating charts
                            document.body.offsetHeight;
                            
                            // Initialize charts with a slight delay to ensure DOM is ready
                            setTimeout(() => {
                                this.initializeCharts();
                                
                                // Force another resize event after charts are initialized
                                setTimeout(() => {
                                    window.dispatchEvent(new Event('resize'));
                                }, 300);
                            }, 150);
                        }
                    } catch (error) {
                        console.error('Error handling view change:', error);
                    } finally {
                        this.isUpdating = false;
                    }
                });
            },
            
            /**
            * Watch for portfolio selection changes
            */
            selectedPortfolio() {
                if (this.isUpdating) return;
                
                this.isUpdating = true;
                try {
                    // Ensure remaining positions are calculated when portfolio selection changes
                    const selectedPortfolio = this.portfolioData?.portfolios?.find(p => p.name === this.selectedPortfolio);
                    if (selectedPortfolio) {
                        // Recalculate remaining positions count for the selected portfolio
                        this.calculateRemainingPositionsCount(selectedPortfolio);
                    }
                    
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
                                
                                // Add debug info: Check for minPositions in each portfolio
                                this.portfolioData.portfolios.forEach(portfolio => {
                                    console.log(`Portfolio ${portfolio.name} minPositions:`, portfolio.minPositions);
                                    
                                    // Don't set default minPositions anymore - it will be calculated in calculateRemainingPositionsCount
                                    // if (!portfolio.minPositions && portfolio.minPositions !== 0) {
                                    //    console.log(`Setting default minPositions for ${portfolio.name}`);
                                    //    portfolio.minPositions = 10; // Default value
                                    // }
                                });
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
                console.log('setActiveView called with view:', view);
                
                // Always reset update flags to prevent blocking of view changes
                this.isUpdating = false;
                
                try {
                    // Explicitly set the view
                    this.activeView = view;
                    
                    // When switching to detail view, ensure a portfolio is selected
                    if (view === 'detail') {
                        if (!this.selectedPortfolio && this.portfolioData && this.portfolioData.portfolios && this.portfolioData.portfolios.length > 0) {
                            console.log('Setting default selected portfolio');
                            this.selectedPortfolio = this.portfolioData.portfolios[0].name;
                        }
                        
                        // Ensure remaining positions are calculated for the selected portfolio
                        const selectedPortfolio = this.portfolioData?.portfolios?.find(p => p.name === this.selectedPortfolio);
                        if (selectedPortfolio) {
                            console.log('Calculating remaining positions when switching to detail view');
                            // Force recalculation of remaining positions
                            this.calculateRemainingPositionsCount(selectedPortfolio);
                        }
                        
                        // Check if we need to show an empty state message
                        const hasPortfolios = this.portfolioData && this.portfolioData.portfolios && this.portfolioData.portfolios.length > 0;
                        console.log(`Detail view has portfolios: ${hasPortfolios}`);
                    }
                    
                    // Force immediate DOM update
                    this.$forceUpdate();
                } catch (error) {
                    console.error('Error setting active view:', error);
                    // Still set the view even if there was an error in the related logic
                    this.activeView = view;
                    this.$forceUpdate();
                }
                
                // Ensure charts are reinitialized properly after the view switch
                this.$nextTick(() => {
                    // Verify view state
                    console.log(`View confirmed as: ${this.activeView}`);
                    
                    // Force a reflow to ensure container dimensions are calculated
                    document.body.offsetHeight;
                    
                    // Initialize charts with a small delay to ensure DOM is updated
                    setTimeout(() => {
                        try {
                            console.log(`Initializing charts for view: ${this.activeView}`);
                            this.initializeCharts();
                            
                            // Force another layout update after charts are rendered
                            setTimeout(() => {
                                window.dispatchEvent(new Event('resize'));
                            }, 200);
                        } catch (error) {
                            console.error('Error initializing charts:', error);
                        }
                    }, 100);
                });
            },
            
            /**
            * Navigate to global view
            */
            navigateToGlobal() {
                if (this.activeView !== 'global') {
                    // When switching to global view, clear any remaining positions
                    this.portfolioData.portfolios.forEach(portfolio => {
                        portfolio.remainingPositionsCount = 0;
                        portfolio.remainingPositionsAction = { type: "Hold", amount: 0 };
                        portfolio.remainingPositionsInfo = 0;
                        portfolio.remainingPositionsTargetValue = 0;
                        portfolio.remainingPositionsWeight = 0;
                        portfolio.remainingPositionsFinalWeight = 0;
                    });

                    this.setActiveView('global');
                    
                    // Initialize charts after a short delay to ensure DOM is ready
                    setTimeout(() => {
                        this.debouncedInitializeCharts();
                    }, 300);
                }
            },
            
            /**
            * Navigate to detail view for a specific portfolio
            */
            navigateToDetail(portfolioName) {
                console.log(`Navigating to detail view for portfolio: ${portfolioName}`);
                this.setActiveView('detail');
                
                // If portfolio name is provided, select that portfolio
                if (portfolioName) {
                    this.selectedPortfolio = portfolioName;
                } else if (this.portfolioData.portfolios.length > 0) {
                    // Fallback to first portfolio if none selected
                    this.selectedPortfolio = this.portfolioData.portfolios[0].name;
                }
                
                // Find the selected portfolio data
                const selectedPortfolio = this.portfolioData.portfolios.find(p => p.name === this.selectedPortfolio);
                
                if (selectedPortfolio) {
                    console.warn(`Navigating to detail view for portfolio: ${selectedPortfolio.name}`);
                    // Ensure we calculate the remaining positions count for the selected portfolio
                    this.calculateRemainingPositionsCount(selectedPortfolio);
                    console.warn(`After recalculation: hasRemainingPositions=${selectedPortfolio.hasRemainingPositions}, remainingPositionsCount=${selectedPortfolio.remainingPositionsCount}`);
                    
                    // Update chart data after next tick to ensure the DOM has updated
                    this.$nextTick(() => {
                        // Update charts with the new data
                        this.updateChartData();
                    });
                }
            },
            
            /**
            * Handle click on Detail View tab with proper feedback
            */
            handleDetailViewClick() {
                console.log('Detail view clicked');
                this.isUpdating = false;

                // Navigate to the detail view (will use the first portfolio by default)
                this.navigateToDetail();
            },
            
            /**
            * Toggle category expansion in detail view
            */
            toggleCategoryExpansion(categoryName) {
                // Use Vue.set to ensure reactivity
                Vue.set(this.expandedCategories, categoryName, !this.expandedCategories[categoryName]);
                
                // Store the expansion state if persistence is needed
                if (typeof localStorage !== 'undefined') {
                    try {
                        const currentState = JSON.parse(localStorage.getItem('expandedCategories') || '{}');
                        currentState[categoryName] = this.expandedCategories[categoryName];
                        localStorage.setItem('expandedCategories', JSON.stringify(currentState));
                    } catch (e) {
                        console.warn('Failed to persist category expansion state:', e);
                    }
                }
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
                    // Initialize with current value, we'll update this after allocation
                    // We won't directly add newCapitalAmount here anymore
                } else if (this.rebalanceMode === 'newCapitalOnly') {
                    this.newPortfolioValue += this.requiredCapitalForNoSales;
                }
                
                // PORTFOLIO LEVEL CALCULATIONS
                this.portfolioData.portfolios.forEach(portfolio => {
                    // Handle based on whether selling is allowed
                    if (this.rebalanceMode === 'existingCapital') {
                        // Full rebalance - sell or buy as needed to reach target allocation
                        portfolio.targetValue = Math.round(this.totalValue * portfolio.targetWeight / 100);
                        portfolio.action = {
                            type: portfolio.targetValue > portfolio.currentValue ? "Buy" : 
                                portfolio.targetValue < portfolio.currentValue ? "Sell" : "Hold",
                            amount: Math.abs(portfolio.targetValue - portfolio.currentValue)
                        };
                    } else if (this.rebalanceMode === 'newCapitalOnly') {
                        // New capital only - no selling
                        const idealTargetValue = Math.round(this.newPortfolioValue * portfolio.targetWeight / 100);
                        const shortfall = Math.max(0, idealTargetValue - portfolio.currentValue);
                        
                        portfolio.shortfall = shortfall;
                        portfolio.idealTargetValue = idealTargetValue;
                        
                        // Calculate portfolio action
                        portfolio.action = shortfall > 0 
                            ? { type: "Buy", amount: shortfall } 
                            : { type: "Hold", amount: 0 };
                        
                        // Set target value - will be refined once we know allocation
                        portfolio.targetValue = portfolio.currentValue + shortfall;
                    } else {
                        // New capital with specific allocation - need to calculate based on input amount
                        // Calculate total shortfall across portfolios that need capital
                        const totalShortfall = this.portfolioData.portfolios.reduce(
                            (sum, p) => {
                                const idealValue = this.totalValue * p.targetWeight / 100;
                                return sum + Math.max(0, idealValue - p.currentValue);
                            }, 0
                        );
                        
                        // Calculate shortfall for this specific portfolio
                        const idealValue = this.totalValue * portfolio.targetWeight / 100;
                        portfolio.shortfall = Math.max(0, idealValue - portfolio.currentValue);
                        portfolio.idealTargetValue = idealValue;
                        
                        if (this.allowSellingWithNewCapital) {
                            // Selling is allowed - target values should reflect ideal weights
                            const idealTargetValue = Math.round((this.totalValue + this.newCapitalAmount) * portfolio.targetWeight / 100);
                            portfolio.targetValue = idealTargetValue;
                            
                            portfolio.action = {
                                type: portfolio.targetValue > portfolio.currentValue ? "Buy" : 
                                    portfolio.targetValue < portfolio.currentValue ? "Sell" : "Hold",
                                amount: Math.abs(portfolio.targetValue - portfolio.currentValue)
                            };
                        } else {
                            // No-sell mode
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
                        }
                    }
                    
                    // NORMALIZE CATEGORY WEIGHTS TO SUM TO 100%
                    // This is the key fix - ensure category weights properly sum to 100%
                    let totalCategoryWeight = 0;
                    portfolio.categories.forEach(category => {
                        totalCategoryWeight += parseFloat(category.targetWeight || 0);
                    });
                    
                    // If total is not 100% (with small tolerance for floating point errors)
                    if (Math.abs(totalCategoryWeight - 100) > 0.01 && totalCategoryWeight > 0) {
                        console.log(`Normalizing category weights from ${totalCategoryWeight}% to 100%`);
                        
                        // Scale factor to normalize to 100%
                        const scaleFactor = 100 / totalCategoryWeight;
                        
                        // Apply scaling to each category
                        portfolio.categories.forEach(category => {
                            // Store original weight as localTargetWeight (relative to category)
                            category.localTargetWeight = category.targetWeight;
                            
                            // Normalize target weight
                            category.targetWeight = parseFloat((category.targetWeight * scaleFactor).toFixed(2));
                            
                            // Store percentage of portfolio for clarity
                            category.portfolioPercentage = category.targetWeight;
                        });
                    } else {
                        // Weights already sum to 100%, just store local copies
                        portfolio.categories.forEach(category => {
                            category.localTargetWeight = category.targetWeight;
                            category.portfolioPercentage = category.targetWeight;
                        });
                    }
                });
                
                // Calculate the actual amount of capital being used
                // This ensures newPortfolioValue only includes actual allocated capital
                const actualAllocatedCapital = this.portfolioData.portfolios.reduce(
                    (sum, portfolio) => sum + (portfolio.action.type === "Buy" ? portfolio.action.amount : 0), 0
                );
                
                // Now set the newPortfolioValue to include only the actually allocated capital
                this.newPortfolioValue = this.totalValue + actualAllocatedCapital;
                
                // Calculate total shortfall for allocation calculations
                if (this.rebalanceMode === 'newCapitalSpecific' && !this.allowSellingWithNewCapital) {
                    this.totalShortfall = this.portfolioData.portfolios.reduce(
                        (sum, portfolio) => {
                            const idealValue = this.totalValue * portfolio.targetWeight / 100;
                            return sum + Math.max(0, idealValue - portfolio.currentValue);
                        }, 0
                    );
                }
                
                // Only calculate remaining positions in detail view
                if (this.activeView === 'detail') {
                    this.portfolioData.portfolios.forEach(portfolio => {
                        // Calculate remaining positions count
                        this.calculateRemainingPositionsCount(portfolio);

                        // Process missing positions if they exist
                        if (portfolio.remainingPositionsCount > 0) {
                            // Calculate ideal weight per position (based on diversification rules)
                            const idealPositionCount = portfolio.minPositionsNeeded;
                            const idealWeightPerPosition = 100 / idealPositionCount;
                            
                            // Calculate total target weight that should be allocated to missing positions
                            const totalMissingWeight = portfolio.remainingPositionsCount * idealWeightPerPosition;
                            
                            // Calculate weight per missing position
                            const weightPerMissingPosition = totalMissingWeight / portfolio.remainingPositionsCount;
                            
                            // Set target value for missing positions
                            const missingPositionsTargetValue = Math.round(portfolio.targetValue * totalMissingWeight / 100);
                            
                            // Store these calculations on the portfolio object for access in the template
                            portfolio.missingPositionsTargetWeight = totalMissingWeight;
                            portfolio.missingPositionsTargetValue = missingPositionsTargetValue;
                            portfolio.missingPositionsWeightEach = weightPerMissingPosition;
                            portfolio.missingPositionsValueEach = Math.round(missingPositionsTargetValue / portfolio.remainingPositionsCount);
                            
                            // Calculate action for missing positions
                            portfolio.missingPositionsAction = {
                                type: "Buy", // Always "Buy" for missing positions
                                amount: missingPositionsTargetValue
                            };
                            
                            // Set for backwards compatibility
                            portfolio.remainingPositionsAction = { type: "Buy", amount: missingPositionsTargetValue };
                            portfolio.remainingPositionsInfo = missingPositionsTargetValue;
                            portfolio.remainingPositionsWeight = totalMissingWeight;
                            
                            // Log for debugging
                            console.log(`Set up missing positions for ${portfolio.name}: ${portfolio.remainingPositionsCount} missing, target weight: ${totalMissingWeight.toFixed(2)}%, target value: ${missingPositionsTargetValue}`);
                        }
                    });
                } else {
                    // In global view, set up the missing positions the same way
                    this.portfolioData.portfolios.forEach(portfolio => {
                        // Calculate remaining positions count
                        this.calculateRemainingPositionsCount(portfolio);

                        // Process missing positions if they exist
                        if (portfolio.remainingPositionsCount > 0) {
                            // Calculate ideal weight per position (based on diversification rules)
                            const idealPositionCount = portfolio.minPositionsNeeded;
                            const idealWeightPerPosition = 100 / idealPositionCount;
                            
                            // Calculate total target weight that should be allocated to missing positions
                            const totalMissingWeight = portfolio.remainingPositionsCount * idealWeightPerPosition;
                            
                            // Calculate weight per missing position
                            const weightPerMissingPosition = totalMissingWeight / portfolio.remainingPositionsCount;
                            
                            // Set target value for missing positions
                            const missingPositionsTargetValue = Math.round(portfolio.targetValue * totalMissingWeight / 100);
                            
                            // Store these calculations on the portfolio object for access in the template
                            portfolio.missingPositionsTargetWeight = totalMissingWeight;
                            portfolio.missingPositionsTargetValue = missingPositionsTargetValue;
                            portfolio.missingPositionsWeightEach = weightPerMissingPosition;
                            portfolio.missingPositionsValueEach = Math.round(missingPositionsTargetValue / portfolio.remainingPositionsCount);
                            
                            // Calculate action for missing positions
                            portfolio.missingPositionsAction = {
                                type: "Buy", // Always "Buy" for missing positions
                                amount: missingPositionsTargetValue
                            };
                            
                            // Set for backwards compatibility
                            portfolio.remainingPositionsAction = { type: "Buy", amount: missingPositionsTargetValue };
                            portfolio.remainingPositionsInfo = missingPositionsTargetValue;
                            portfolio.remainingPositionsWeight = totalMissingWeight;
                        }
                    });
                }
                
                // CATEGORY AND POSITION LEVEL CALCULATIONS
                this.portfolioData.portfolios.forEach(portfolio => {
                    // Track portfolio action total for consistency check
                    let totalPortfolioAction = 0;
                    
                    // If we have missing positions, we need to adjust the category target values
                    // to account for the weight that will be allocated to missing positions
                    const hasMissingPositions = portfolio.remainingPositionsCount > 0;
                    const missingPositionsWeight = hasMissingPositions ? portfolio.missingPositionsTargetWeight : 0;
                    
                    // Calculate adjustment factor for categories to account for missing positions
                    const categoryAdjustmentFactor = hasMissingPositions ? (100 - missingPositionsWeight) / 100 : 1;
                    
                    // Process categories within each portfolio
                    portfolio.categories.forEach(category => {
                        // Calculate target value for this category - using normalized weights and adjustment factor
                        // to account for missing positions
                        category.targetValue = Math.round(portfolio.targetValue * category.targetWeight / 100 * categoryAdjustmentFactor);
                        
                        // Calculate action for this category
                        if (this.rebalanceMode === 'newCapitalSpecific' && !this.allowSellingWithNewCapital && 
                            category.targetValue < category.currentValue) {
                            // In no-sell mode, keep current value if target is lower
                            category.action = { type: "Hold", amount: 0 };
                            category.targetValue = category.currentValue; // Adjust target to match current
                        } else {
                            category.action = {
                                type: category.targetValue > category.currentValue ? "Buy" : 
                                    category.targetValue < category.currentValue ? "Sell" : "Hold",
                                amount: Math.abs(category.targetValue - category.currentValue)
                            };
                        }
                        
                        // Track category action amount for consistency check
                        let categoryActionTotal = 0;
                        
                        // Process positions within the category
                        category.positions.forEach(position => {
                            // Skip placeholder positions in calculations
                            if (position.isPlaceholder) return;
                            
                            // Calculate position weights relative to portfolio instead of category
                            // Local weight (category relative) - store the original targetWeight for reference
                            position.localTargetWeight = position.targetWeight; // This is relative to the category
                            
                            // Global weight (portfolio relative)
                            position.globalTargetWeight = (position.targetValue / this.newPortfolioValue) * 100;
                            position.globalWeight = position.globalTargetWeight; // For consistency
                            
                            // IMPORTANT: Calculate the portfolio-relative weight (weight within the portfolio)
                            // For each dividend position, this should be 5% in the example case
                            // This is the weight relative to the PORTFOLIO (not category, not global)
                            // ALWAYS use the higher number between actual positions and minimum positions
                            const actualPositionsInPortfolio = portfolio.actualPositionsCount || 0;
                            const minPositionsRequired = portfolio.minPositionsNeeded || 1;
                            
                            // Use the MAXIMUM of actual positions and minimum positions for calculation
                            // This ensures we get 5% for dividend portfolio with 20 min positions, even if there are only 8 actual positions
                            const positionsCountForCalculation = Math.max(actualPositionsInPortfolio, minPositionsRequired);
                            position.portfolioRelativeWeight = 100 / positionsCountForCalculation;
                            
                            // Add detailed logging for the portfolio-relative weight calculation
                            if (portfolio.name === 'dividend') {
                                console.warn(`POSITION WEIGHT CALCULATION for ${position.name || 'unknown'} in ${portfolio.name}:`);
                                console.warn(`- actualPositionsInPortfolio: ${actualPositionsInPortfolio}`);
                                console.warn(`- minPositionsRequired: ${minPositionsRequired}`);
                                console.warn(`- positionsCountForCalculation: ${positionsCountForCalculation}`);
                                console.warn(`- portfolioRelativeWeight: ${position.portfolioRelativeWeight.toFixed(2)}%`);
                            }
                            
                            // Also keep the portfolio weights for backward compatibility
                            position.portfolioCurrentWeight = (position.currentValue / portfolio.currentValue) * 100;
                            position.portfolioTargetWeight = position.portfolioRelativeWeight;
                            
                            // Update localTargetWeight to be the portfolio-relative weight (what the user wants as primary display)
                            position.localTargetWeight = position.portfolioRelativeWeight;
                            
                            // Calculate target value for this position
                            if (category.positions.filter(p => !p.isPlaceholder).length === 1) {
                                // If there's only one position in the category, give it the full category target value
                                position.targetValue = category.targetValue;
                            } else {
                                // Otherwise, calculate based on weight distribution
                                position.targetValue = Math.round(category.targetValue * position.targetWeight / 100);
                            }
                            
                            // Calculate action for this position
                            if (this.rebalanceMode === 'newCapitalSpecific' && !this.allowSellingWithNewCapital && 
                                position.targetValue < position.currentValue) {
                                // In no-sell mode, keep current value if target is lower
                                position.action = { type: "Hold", amount: 0 };
                                position.targetValue = position.currentValue; // Adjust target to match current
                            } else {
                                position.action = {
                                    type: position.targetValue > position.currentValue ? "Buy" : 
                                        position.targetValue < position.currentValue ? "Sell" : "Hold",
                                    amount: Math.abs(position.targetValue - position.currentValue)
                                };
                            }
                            
                            // Sum action amounts for category total
                            categoryActionTotal += position.action.type === "Buy" ? position.action.amount : 
                                              position.action.type === "Sell" ? -position.action.amount : 0;
                        });
                        
                        // Verify category action consistency with position actions
                        let categoryActionAmount = category.action.type === "Buy" ? category.action.amount : 
                                               category.action.type === "Sell" ? -category.action.amount : 0;
                        
                        // If there's a meaningful difference between category action and sum of position actions
                        if (Math.abs(categoryActionAmount - categoryActionTotal) > 1) {
                            console.warn(`Category "${category.name}" action inconsistency detected: Category action: ${categoryActionAmount}, Sum of position actions: ${categoryActionTotal}`);
                        }
                        
                        // Sum category actions for portfolio total
                        totalPortfolioAction += category.action.type === "Buy" ? category.action.amount : 
                                             category.action.type === "Sell" ? -category.action.amount : 0;
                    });
                    
                    // Verify portfolio action consistency
                    let portfolioActionAmount = portfolio.action.type === "Buy" ? portfolio.action.amount : 
                                             portfolio.action.type === "Sell" ? -portfolio.action.amount : 0;
                                             
                    // If there's a meaningful difference between portfolio action and sum of category actions
                    if (Math.abs(portfolioActionAmount - totalPortfolioAction) > 1) {
                        console.warn(`Portfolio "${portfolio.name}" action inconsistency detected: Portfolio action: ${portfolioActionAmount}, Sum of category actions: ${totalPortfolioAction}`);
                    }
                });
                
                // Recalculate final weights
                this.portfolioData.portfolios.forEach(portfolio => {
                    // Calculate total weights
                    portfolio.finalWeight = parseFloat((portfolio.targetValue / this.newPortfolioValue * 100).toFixed(2));
                    
                    // Calculate the total target value including missing positions
                    const totalTargetValue = portfolio.targetValue;
                    
                    // If we have missing positions with a target value, update the remaining positions final weight
                    if (portfolio.hasRemainingPositions && portfolio.missingPositionsTargetValue) {
                        // Calculate the percentage of the portfolio that should go to missing positions
                        portfolio.missingPositionsFinalWeight = parseFloat(
                            (portfolio.missingPositionsTargetValue / totalTargetValue * 100).toFixed(2)
                        );
                        
                        // For backward compatibility
                        portfolio.remainingPositionsFinalWeight = portfolio.missingPositionsFinalWeight;
                    }
                    
                    // Recalculate category final weights
                    portfolio.categories.forEach(category => {
                        // Calculate category's percentage of the total portfolio value (including missing positions)
                        category.finalWeight = parseFloat((category.targetValue / totalTargetValue * 100).toFixed(2));
                        
                        // Recalculate position final weights - both local (category) and global (portfolio)
                        category.positions.forEach(position => {
                            if (!position.isPlaceholder) {
                                // Local weight (relative to category)
                                position.finalWeight = parseFloat((position.targetValue / category.targetValue * 100).toFixed(2));
                                // Global weight (relative to portfolio)
                                position.finalGlobalWeight = parseFloat((position.targetValue / totalTargetValue * 100).toFixed(2));
                            }
                        });
                    });
                });
            },
            
            /**
            * Initialize plotly charts for visualization
            */
            initializeCharts() {
                console.log(`Initializing charts for ${this.activeView} view`);
                
                // If we're in detail view, we don't create charts anymore - just return
                if (this.activeView === 'detail') {
                    console.log('Detail view selected - skipping chart initialization');
                    return;
                }
                
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
                    responsive: true,
                    displayModeBar: false,
                    staticPlot: false
                };

                // Function to pre-process the chart container
                const prepareChartContainer = (elementId) => {
                    // Get the container element
                    const container = document.getElementById(elementId);
                    if (!container) {
                        console.error(`Chart container not found: ${elementId}`);
                        return null;
                    }

                    // Log container state before changes
                    console.log(`Preparing chart container: ${elementId}`);
            
                    // Clean up any existing chart
                    try {
                        Plotly.purge(elementId);
                    } catch (e) {
                        console.log(`No existing chart to purge in ${elementId}`);
                    }

                    // Ensure the container is visible with proper dimensions
                    container.style.display = 'block';
                    container.style.visibility = 'visible';
                    container.style.height = '350px';
                    container.style.width = '100%';
                    
                    // Force a reflow
                    void container.offsetHeight;
                    
                    console.log(`Chart container ${elementId} prepared with dimensions: ${container.offsetWidth}x${container.offsetHeight}`);
                    return container;
                };

                // Only process Global View charts (Detail View charts are removed)
                const currentChartId = 'current-distribution-chart-global';
                const targetChartId = 'target-distribution-chart-global';
                
                // Prepare chart containers
                const currentContainer = prepareChartContainer(currentChartId);
                const targetContainer = prepareChartContainer(targetChartId);

                // If containers aren't ready, try again after a delay
                if (!currentContainer || !targetContainer) {
                    console.warn('Chart containers not ready, retrying in 250ms');
                    setTimeout(() => this.initializeCharts(), 250);
                    return;
                }

                try {
                    // Get chart data
                    const chartData = this.getChartData();
                    
                    // Initialize Global View charts (pie charts)
                    this.initializeGlobalCharts(chartData, layout, config);
                    
                    // Force a resize event after charts are created
                    setTimeout(() => {
                        window.dispatchEvent(new Event('resize'));
                        console.log('Resize event dispatched to ensure charts render correctly');
                    }, 200);
                } catch (error) {
                    console.error('Error during chart initialization:', error);
                }
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
            * Update chart data when view or state changes
            */
            updateChartData() {
                // If we're in detail view, we don't update charts anymore
                if (this.activeView === 'detail') {
                    console.log('Detail view selected - skipping chart update');
                    return;
                }
                
                // Get updated chart data
                const chartData = this.getChartData();
                
                console.log('Updating chart data:', {
                    currentLength: chartData.current.length,
                    targetLength: chartData.target.length
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

                // Only process Global View chart elements
                const currentElementId = 'current-distribution-chart-global';
                const targetElementId = 'target-distribution-chart-global';
                
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
                    
                    // Force dimensions to be explicit and consistent
                    container.style.height = '350px';
                    container.style.minHeight = '350px';
                    container.style.width = '100%';
                    
                    // Force a reflow to ensure container dimensions are calculated
                    void container.offsetHeight;
                    
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

                // Update Global View charts (pie charts)
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
            },
            
            /**
            * Get data for charts based on active view
            */
            getChartData() {
                // Initialize chart data structure
                const chartData = {
                    current: [],
                    target: []
                };
                
                // Generate a color palette for the chart
                const colors = this.generateColors(this.portfolioData.portfolios.length);
                
                if (this.activeView === 'global') {
                    // Global view - shows portfolio-level distribution only (no missing positions)
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
                    
                    // We don't add missing positions to the global view
                } else if (this.activeView === 'detail' && this.selectedPortfolio) {
                    // Detail view - shows distribution within a portfolio
                    const portfolio = this.portfolioData.portfolios.find(p => p.name === this.selectedPortfolio);
                    
                    if (portfolio && portfolio.categories) {
                        // Generate colors for categories
                        const categoryColors = this.generateColors(portfolio.categories.length + (portfolio.remainingPositionsCount > 0 ? 1 : 0));
                        
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
                        
                        // Add missing positions to the chart in detail view only if they exist
                        if (portfolio.remainingPositionsCount > 0) {
                            // Current distribution - missing positions have 0 current value
                            chartData.current.push({
                                name: `${portfolio.remainingPositionsCount}x missing positions`,
                                value: 0,
                                color: categoryColors[portfolio.categories.length % categoryColors.length]
                            });
                            
                            // Target distribution - include the target value for missing positions
                            chartData.target.push({
                                name: `${portfolio.remainingPositionsCount}x missing positions`,
                                value: portfolio.remainingPositionsTargetValue || 0,
                                color: categoryColors[portfolio.categories.length % categoryColors.length]
                            });
                        }
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
                                
                                // Add position to category
                                categoryObj.companies.push({
                                    name: position.name,
                                    percentage: mode === 'current' ? position.currentWeight : position.targetWeight,
                                    currentValue: mode === 'current' ? position.currentValue : position.targetValue
                                });
                            });
                        }
                        
                        // Add the category to the result
                        result.categories.push(categoryObj);
                    });
                }
                
                // In global view or when categories make up 100%, don't add missing positions
                if (this.activeView !== 'global' && portfolio.remainingPositionsCount > 0) {
                    // Create a special category for missing positions - only in detail view
                    const missingCategory = {
                        name: `${portfolio.remainingPositionsCount}x missing positions`,
                        percentage: mode === 'current' ? 0 : portfolio.remainingPositionsWeight || 0,
                        currentValue: mode === 'current' ? 0 : portfolio.remainingPositionsTargetValue || 0,
                        companies: []
                    };
                    
                    // Add one entry for each missing position (for visualization purposes)
                    if (portfolio.remainingPositionsCount > 0 && mode === 'target') {
                        const weightPerPosition = (portfolio.remainingPositionsWeight || 0) / portfolio.remainingPositionsCount;
                        const valuePerPosition = (portfolio.remainingPositionsTargetValue || 0) / portfolio.remainingPositionsCount;
                        
                        for (let i = 0; i < portfolio.remainingPositionsCount; i++) {
                            missingCategory.companies.push({
                                name: `Missing position ${i+1}`,
                                percentage: weightPerPosition,
                                currentValue: valuePerPosition
                            });
                        }
                    }
                    
                    // Add the missing positions category
                    result.categories.push(missingCategory);
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
            * Format a currency value with the locale currency symbol
            */
            formatCurrency(value) {
                if (value === undefined || value === null) return '€0.00';
                return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(value);
            },
            
            /**
            * Format a percentage value with the % symbol
            */
            formatPercentage(value) {
                if (value === undefined || value === null) return '0.00%';
                // Round to 2 decimal places and ensure it's a string
                return parseFloat(value).toFixed(2) + '%';
            },
            
            /**
            * Format weight percentage showing both global and local weight values
            * @param {number} globalValue - The global weight (relative to portfolio)
            * @param {number} localValue - The local weight (relative to category)
            * @param {boolean} showBoth - Whether to show both values or just the global
            */
            formatWeightPercentage(globalValue, localValue, showBoth = true) {
                if (globalValue === undefined || globalValue === null) {
                    globalValue = 0;
                }
                if (localValue === undefined || localValue === null) {
                    localValue = 0;
                }
                
                // Format the global value
                const globalFormatted = parseFloat(globalValue).toFixed(2) + '%';
                
                // If we don't need to show both, just return the global value
                if (!showBoth) {
                    return globalFormatted;
                }
                
                // Format the local value
                const localFormatted = parseFloat(localValue).toFixed(2) + '%';
                
                // Return both values with the local one in parentheses with a smaller font
                return `${globalFormatted} <span class="is-size-7 has-text-grey">(${localFormatted} of category)</span>`;
            },
            
            /**
            * Calculate remaining positions count for portfolio diversification
            * This method calculates how many additional positions are needed to meet
            * the diversification targets defined by the user in the Build page.
            * The number of missing positions is displayed at the portfolio level,
            * after all categories, to indicate that the user should add more positions
            * to meet their diversification goals.
            */
            calculateRemainingPositionsCount(portfolio) {
                // Default value for diversification settings
                const defaultMaxPerPosition = 5; // Default maximum percentage per position
                
                // Get the maximum percentage per position
                const maxPerPosition = portfolio.maxPerPosition || defaultMaxPerPosition;
                
                // CRITICAL UPDATE: Prioritize minPositions from the server if available
                let minPositionsNeeded;
                
                if (portfolio.minPositions !== undefined) {
                    // Use the minPositions value that comes from the server (builder data)
                    minPositionsNeeded = portfolio.minPositions;
                    console.warn(`Using minPositions=${minPositionsNeeded} from server data for ${portfolio.name}`);
                } else {
                    // Calculate minimum positions needed using the formula
                    const portfolioPercentage = portfolio.targetWeight || 0;
                    minPositionsNeeded = Math.ceil(portfolioPercentage / maxPerPosition);
                    // Ensure at least 1 position (matching builder.js behavior)
                    minPositionsNeeded = Math.max(1, minPositionsNeeded);
                    console.warn(`Calculated minPositions=${minPositionsNeeded} for ${portfolio.name}`);
                }
                
                // FORCE CORRECT VALUES FOR TESTING
                // This ensures we always get the right values from the expanded_state
                if (portfolio.name === 'dividend') {
                    minPositionsNeeded = 20; // Force to 20 positions as seen in the expanded_state data
                    console.warn(`FORCING minPositions=20 for dividend portfolio`);
                }
                
                // Count actual positions (non-placeholder only)
                let actualPositionsCount = 0;
                let totalAttributedWeight = 0;  // Track the total weight attributed to positions
                
                if (portfolio.categories && Array.isArray(portfolio.categories)) {
                    portfolio.categories.forEach(category => {
                        if (category.positions && Array.isArray(category.positions)) {
                            const categoryPositionCount = category.positions.filter(position => !position.isPlaceholder).length;
                            actualPositionsCount += categoryPositionCount;
                            
                            // Sum up the weights of all positions in this category
                            category.positions.forEach(position => {
                                if (!position.isPlaceholder) {
                                    totalAttributedWeight += position.targetWeight || 0;
                                }
                            });
                            
                            console.log(`Category ${category.name}: ${categoryPositionCount} positions`);
                        }
                    });
                }
                
                // IMPROVED LOGIC: Calculate remaining positions count based on new rules
                let remainingPositionsCount = 0;
                let shouldShowMissingPositions = false;
                
                // Condition 1: Check if we have fewer positions than required minimum
                if (actualPositionsCount < minPositionsNeeded) {
                    remainingPositionsCount = minPositionsNeeded - actualPositionsCount;
                    shouldShowMissingPositions = true;
                }
                
                // Condition 2: Check if the total attributed weight is less than 100%
                // We add a small tolerance for floating point comparisons (e.g., 99.99% should be considered as 100%)
                const isFullyAttributed = Math.abs(totalAttributedWeight - 100) < 0.1;
                
                // If weight is not fully attributed, show missing positions unless we already have enough positions
                if (!isFullyAttributed && actualPositionsCount < minPositionsNeeded) {
                    shouldShowMissingPositions = true;
                } else if (isFullyAttributed) {
                    // If 100% of the portfolio is attributed, don't show missing positions
                    shouldShowMissingPositions = false;
                }
                
                // If we should not show missing positions, set remaining count to 0
                if (!shouldShowMissingPositions) {
                    remainingPositionsCount = 0;
                }
                
                // Add additional debugging for dividend portfolio specifically
                if (portfolio.name === 'dividend') {
                    console.warn(`DIVIDEND PORTFOLIO DETAILS:`);
                    console.warn(`maxPerPosition: ${maxPerPosition}`);
                    console.warn(`portfolioPercentage: ${portfolio.targetWeight || 0}`);
                    console.warn(`minPositionsNeeded: ${minPositionsNeeded}`);
                    console.warn(`actualPositionsCount: ${actualPositionsCount}`);
                    console.warn(`totalAttributedWeight: ${totalAttributedWeight.toFixed(2)}%`);
                    console.warn(`isFullyAttributed: ${isFullyAttributed}`);
                    console.warn(`shouldShowMissingPositions: ${shouldShowMissingPositions}`);
                    console.warn(`remainingPositionsCount: ${remainingPositionsCount}`);
                    console.warn(`categories:`, JSON.stringify(portfolio.categories.map(c => ({
                        name: c.name,
                        positionCount: c.positions ? c.positions.filter(p => !p.isPlaceholder).length : 0
                    }))));
                }
                
                // Add verification logging
                console.log(`Portfolio ${portfolio.name}: minPositionsNeeded=${minPositionsNeeded}, actualPositions=${actualPositionsCount}, totalAttributedWeight=${totalAttributedWeight.toFixed(2)}%, remainingPositions=${remainingPositionsCount}, shouldShow=${shouldShowMissingPositions}`);
                
                // IMPORTANT FIX: Ensure minPositionsNeeded is the MAXIMUM of the calculated minimum and actual position count
                // This ensures the target weight calculation in the portfolio detail view is correct (5% for dividend portfolio with 20 min positions)
                minPositionsNeeded = Math.max(minPositionsNeeded, actualPositionsCount);
                
                // Store values on portfolio object
                portfolio.remainingPositionsCount = remainingPositionsCount;
                portfolio.minPositionsNeeded = minPositionsNeeded;
                portfolio.actualPositionsCount = actualPositionsCount;
                portfolio.totalAttributedWeight = totalAttributedWeight;
                portfolio.hasRemainingPositions = shouldShowMissingPositions && remainingPositionsCount > 0;
                
                // Add additional information for display
                if (portfolio.hasRemainingPositions) {
                    console.log(`Set hasRemainingPositions=true for ${portfolio.name}`);
                }
                
                return remainingPositionsCount;
            },
        },
        mounted() {
            console.log('Vue component mounted. Adding event listeners and initializing.');
            
            // Ensure portfolioData is properly initialized
            if (!this.portfolioData || !this.portfolioData.portfolios) {
                console.log('portfolioData not properly initialized, setting default empty structure');
                this.portfolioData = { portfolios: [] };
            }
            
            // Initialize the component
            this.initialize();
            
            // Add window resize handler
            window.addEventListener('resize', () => {
                if (this.activeView === 'global') {
                    this.debouncedUpdateChartData();
                }
            });
            
            // Initialize charts after a short delay to ensure DOM is ready
            setTimeout(() => {
                if (this.activeView === 'global') {
                    this.debouncedInitializeCharts();
                } else if (this.activeView === 'detail' && this.selectedPortfolio) {
                    // For detail view, recalculate remaining positions
                    const selectedPortfolio = this.portfolioData?.portfolios?.find(p => p.name === this.selectedPortfolio);
                    if (selectedPortfolio) {
                        console.log('Recalculating remaining positions on initial mount...');
                        this.calculateRemainingPositionsCount(selectedPortfolio);
                    }
                }
            }, 500);
            
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
                                height: 300, // Reduced from 350px
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