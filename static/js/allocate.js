/**
 * Portfolio Allocation - Main JavaScript file
 * This file handles the portfolio allocation calculation based on user input.
 */

// Debounce function to limit how often a function can be called
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Format number with commas and decimals
function formatNumber(number) {
    return number.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Parse number from string, removing commas
function parseNumber(string) {
    return parseFloat(string.replace(/,/g, '')) || 0;
}

// Update allocation table
function updateAllocationTable(amount) {
    // Your existing table update logic here
    // This should be called whenever the investment amount changes
}

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

    // Portfolio allocation functionality
    class PortfolioAllocator {
        constructor() {
            this.portfolioData = null;
            this.investmentAmount = 0;
            this.init();
        }

        init() {
            this.fetchPortfolioData();
            this.setupEventListeners();
            
            // Initialize tab view
            switchTab('global');
        }

        setupEventListeners() {
            // Add event listener for investment amount input
            const investmentInput = document.getElementById('investment-amount');
            if (investmentInput) {
                // Add input event listener with debounce
                investmentInput.addEventListener('input', debounce((e) => {
                    const amount = parseNumber(e.target.value);
                    this.investmentAmount = amount;
                    this.updateTableCalculations();
                }, 500)); // 500ms delay
                
                // Format number as user types
                investmentInput.addEventListener('input', function(e) {
                    const value = e.target.value.replace(/[^\d.]/g, '');
                    const number = parseFloat(value) || 0;
                    e.target.value = formatNumber(number);
                });
            }

            // Add event listener for recalculate button
            const recalculateBtn = document.getElementById('recalculate-btn');
            if (recalculateBtn) {
                recalculateBtn.addEventListener('click', () => {
                    this.updateTableCalculations();
                });
            }
        }

        async fetchPortfolioData() {
            try {
                const response = await fetch('/portfolio/api/allocate/portfolio-data');
                if (!response.ok) {
                    throw new Error('Failed to fetch portfolio data');
                }
                
                this.portfolioData = await response.json();
                this.renderPortfolioTable();
                this.renderCharts();
            } catch (error) {
                console.error('Error fetching portfolio data:', error);
                document.getElementById('portfolio-table-container').innerHTML = `
                    <div class="alert alert-danger">
                        Failed to load portfolio data: ${error.message}
                    </div>
                `;
            }
        }

        formatCurrency(value) {
            return new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'EUR',
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }).format(value);
        }

        formatPercentage(value) {
            return new Intl.NumberFormat('en-US', {
                style: 'percent',
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }).format(value / 100);
        }

        renderPortfolioTable() {
            if (!this.portfolioData || !this.portfolioData.portfolios || this.portfolioData.portfolios.length === 0) {
                document.getElementById('portfolio-table-container').innerHTML = `
                    <div class="alert alert-warning">No portfolio data available</div>
                `;
                return;
            }

            // Filter out portfolios with current value of 0
            const filteredPortfolios = this.portfolioData.portfolios.filter(portfolio => 
                portfolio.currentValue !== 0 && portfolio.currentValue !== null
            );

            // If all portfolios were filtered out, show a message
            if (filteredPortfolios.length === 0) {
                document.getElementById('portfolio-table-container').innerHTML = `
                    <div class="alert alert-warning">No portfolios with non-zero values available</div>
                `;
                return;
            }

            // Calculate total current value across all portfolios
            const totalCurrentValue = filteredPortfolios.reduce(
                (sum, portfolio) => sum + (portfolio.currentValue || 0), 0
            );

            // Generate table HTML
            let tableHTML = `
            <div class="table-responsive">
                <table class="table table-striped table-hover">
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Current Value</th>
                            <th>Current Allocation</th>
                            <th>Target Allocation</th>
                            <th>Target Value</th>
                            <th>Actions</th>
                            <th>Value After Action</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            // Track totals for the summary row
            let totalTargetValue = 0;
            let totalAction = 0;
            let totalValueAfter = 0;

            filteredPortfolios.forEach(portfolio => {
                // Calculate current allocation percentage
                const currentAllocation = totalCurrentValue > 0 
                    ? (portfolio.currentValue / totalCurrentValue) * 100 
                    : 0;
                
                // Calculate target value
                const targetValue = portfolio.targetValue || 0;
                
                // Calculate action (how much to buy/sell)
                const discrepancy = targetValue - portfolio.currentValue;
                let action = 0;
                
                if (this.investmentAmount > 0) {
                    // Distribute investment amount proportionally to discrepancies
                    if (discrepancy > 0) {
                        // Calculate proportion based on positive discrepancies only
                        const totalPositiveDiscrepancy = filteredPortfolios
                            .filter(p => (p.targetValue || 0) - p.currentValue > 0)
                            .reduce((sum, p) => sum + ((p.targetValue || 0) - p.currentValue), 0);
                        
                        if (totalPositiveDiscrepancy > 0) {
                            action = (discrepancy / totalPositiveDiscrepancy) * this.investmentAmount;
                        }
                    }
                }
                
                // Calculate value after action
                const valueAfterAction = portfolio.currentValue + action;

                // Determine action class for styling
                let actionClass = "actions-neutral";
                let actionText = "No action";
                
                if (action > 0) {
                    actionClass = "actions-positive";
                    actionText = `Buy ${this.formatCurrency(action)}`;
                } else if (action < 0) {
                    actionClass = "actions-negative";
                    actionText = `Sell ${this.formatCurrency(Math.abs(action))}`;
                }

                // Generate row HTML
                tableHTML += `
                    <tr>
                        <td>${portfolio.name}</td>
                        <td class="current-value">${this.formatCurrency(portfolio.currentValue || 0)}</td>
                        <td>${this.formatPercentage(currentAllocation)}</td>
                        <td>${this.formatPercentage(portfolio.targetWeight || 0)}</td>
                        <td class="target-value">${this.formatCurrency(targetValue)}</td>
                        <td class="${actionClass}">${actionText}</td>
                        <td class="value-after">${this.formatCurrency(valueAfterAction)}</td>
                    </tr>
                `;

                // Update totals
                totalTargetValue += targetValue;
                totalAction += action;
                totalValueAfter += valueAfterAction;
            });

            // Add a total row
            tableHTML += `
                <tr class="table-primary fw-bold">
                    <td>Total</td>
                    <td class="current-value">${this.formatCurrency(totalCurrentValue)}</td>
                    <td>100%</td>
                    <td>100%</td>
                    <td class="target-value">${this.formatCurrency(totalTargetValue)}</td>
                    <td>${this.formatCurrency(totalAction)}</td>
                    <td class="value-after">${this.formatCurrency(totalValueAfter)}</td>
                </tr>
            `;

            // Close table HTML
            tableHTML += `
                    </tbody>
                </table>
            </div>
            `;

            // Insert table into DOM
            document.getElementById('portfolio-table-container').innerHTML = tableHTML;
        }

        updateTableCalculations() {
            // Re-render the table with updated investment amount
            this.renderPortfolioTable();
            this.renderCharts();
        }

        renderCharts() {
            if (!this.portfolioData || !this.portfolioData.portfolios || this.portfolioData.portfolios.length === 0) {
                return;
            }
            
            // Render detailed overview chart and tables
            this.renderDetailedView();
        }

        renderDetailedView() {
            const detailedChartContainer = document.getElementById('detailedChart');
            const detailedTablesContainer = document.getElementById('detailed-tables-container');
            
            if (!detailedChartContainer || !detailedTablesContainer) return;

            // Filter out portfolios with current value of 0
            const filteredPortfolios = this.portfolioData.portfolios.filter(portfolio => 
                portfolio.currentValue !== 0 && portfolio.currentValue !== null
            );

            // Prepare data for the detailed chart
            const allCategories = [];
            const portfolioColors = [
                'rgba(54, 162, 235, 0.8)',
                'rgba(255, 99, 132, 0.8)',
                'rgba(75, 192, 192, 0.8)',
                'rgba(255, 159, 64, 0.8)',
                'rgba(153, 102, 255, 0.8)',
                'rgba(255, 205, 86, 0.8)',
                'rgba(201, 203, 207, 0.8)'
            ];

            // Extract categories data
            filteredPortfolios.forEach((portfolio, index) => {
                const color = portfolioColors[index % portfolioColors.length];
                
                if (portfolio.categories && portfolio.categories.length > 0) {
                    portfolio.categories.forEach(category => {
                        allCategories.push({
                            portfolio: portfolio.name,
                            category: category.name,
                            value: category.currentValue || 0,
                            color: color
                        });
                    });
                }
            });

            // Create detailed chart
            if (typeof Chart !== 'undefined' && allCategories.length > 0) {
                // Clear previous chart
                while (detailedChartContainer.firstChild) {
                    detailedChartContainer.removeChild(detailedChartContainer.firstChild);
                }
                
                const canvas = document.createElement('canvas');
                detailedChartContainer.appendChild(canvas);
                
                new Chart(canvas, {
                    type: 'pie',
                    data: {
                        labels: allCategories.map(c => `${c.portfolio} - ${c.category}`),
                        datasets: [{
                            data: allCategories.map(c => c.value),
                            backgroundColor: allCategories.map(c => c.color),
                            borderColor: 'white',
                            borderWidth: 1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'right',
                                labels: {
                                    boxWidth: 15,
                                    font: {
                                        size: 11
                                    }
                                }
                            }
                        }
                    }
                });
            } else {
                detailedChartContainer.innerHTML = `
                    <div class="alert alert-info">
                        No detailed category data available or Chart.js library not loaded.
                    </div>
                `;
            }

            // Generate detailed tables HTML
            let tablesHTML = '';
            
            filteredPortfolios.forEach(portfolio => {
                // Calculate action for this portfolio
                const discrepancy = portfolio.targetValue - portfolio.currentValue;
                let portfolioAction = 0;
                
                if (this.investmentAmount > 0 && discrepancy > 0) {
                    const totalPositiveDiscrepancy = filteredPortfolios
                        .filter(p => (p.targetValue || 0) - p.currentValue > 0)
                        .reduce((sum, p) => sum + ((p.targetValue || 0) - p.currentValue), 0);
                    
                    if (totalPositiveDiscrepancy > 0) {
                        portfolioAction = (discrepancy / totalPositiveDiscrepancy) * this.investmentAmount;
                    }
                }
                
                // Create portfolio table
                tablesHTML += `
                    <div class="card mt-3">
                        <div class="card-header">
                            <h5 class="card-title">${portfolio.name}</h5>
                        </div>
                        <div class="card-body">
                            <div class="table-responsive">
                                <table class="table table-striped table-hover">
                                    <thead>
                                        <tr>
                                            <th>Category/Position</th>
                                            <th>Current Value</th>
                                            <th>Target Value</th>
                                            <th>Allocation</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                `;
                
                // Add categories and positions
                if (portfolio.categories && portfolio.categories.length > 0) {
                    portfolio.categories.forEach(category => {
                        // Add category row
                        tablesHTML += `
                            <tr class="table-active">
                                <td><strong>${category.name}</strong></td>
                                <td>${this.formatCurrency(category.currentValue || 0)}</td>
                                <td>${this.formatCurrency(category.targetValue || 0)}</td>
                                <td>${this.formatPercentage(category.targetWeight || 0)}</td>
                            </tr>
                        `;
                        
                        // Add position rows
                        if (category.positions && category.positions.length > 0) {
                            category.positions.forEach(position => {
                                tablesHTML += `
                                    <tr>
                                        <td style="padding-left: 2rem;">${position.name}</td>
                                        <td>${this.formatCurrency(position.currentValue || 0)}</td>
                                        <td>${this.formatCurrency(position.targetValue || 0)}</td>
                                        <td>${this.formatPercentage(position.targetWeight || 0)}</td>
                                    </tr>
                                `;
                            });
                        }
                    });
                } else {
                    tablesHTML += `
                        <tr>
                            <td colspan="4" class="text-center">No detailed data available for this portfolio</td>
                        </tr>
                    `;
                }
                
                // Close table
                tablesHTML += `
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                `;
            });
            
            // Insert tables into DOM
            detailedTablesContainer.innerHTML = tablesHTML;
        }
    }

    // Initialize portfolio allocator
    const allocator = new PortfolioAllocator();
});