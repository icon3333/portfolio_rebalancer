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

document.addEventListener('DOMContentLoaded', function () {
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
            this.categoriesExpanded = new Set(); // Track expanded categories
            this.selectedPortfolio = null; // Track selected portfolio
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
                // Combined event listener for formatting and updating calculations
                investmentInput.addEventListener('input', (e) => {
                    // Clean and format the input value
                    const cleanValue = e.target.value.replace(/[^\d.]/g, '');
                    const number = parseFloat(cleanValue) || 0;

                    // Format the display value
                    e.target.value = formatNumber(number);

                    // Update the investment amount and trigger calculations immediately
                    this.investmentAmount = number;
                    this.updateTableCalculations();
                    this.renderDetailedView(); // Update detailed view when investment amount changes
                });
            }

            // Add portfolio selection change listener
            const portfolioSelect = document.getElementById('portfolio-select');
            if (portfolioSelect) {
                portfolioSelect.addEventListener('change', (e) => {
                    this.selectedPortfolio = e.target.value;
                    this.renderDetailedView();
                });
            }
        }

        async fetchPortfolioData() {
            try {
                const response = await fetch('/portfolio/api/allocate/portfolio-data');
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                this.portfolioData = await response.json();
                if (!this.portfolioData || !this.portfolioData.portfolios) {
                    throw new Error('Invalid portfolio data received');
                }

                this.renderPortfolioTable();
                this.populatePortfolioSelect();
                this.renderDetailedView();
            } catch (error) {
                console.error('Error fetching portfolio data:', error);
                this.showError('Failed to load portfolio data. Please try again later.');
            }
        }

        populatePortfolioSelect() {
            const portfolioSelect = document.getElementById('portfolio-select');
            if (!portfolioSelect || !this.portfolioData || !this.portfolioData.portfolios) return;

            // Clear existing options
            portfolioSelect.innerHTML = '';

            // Add default option
            const defaultOption = document.createElement('option');
            defaultOption.value = '';
            defaultOption.textContent = 'Select a portfolio';
            portfolioSelect.appendChild(defaultOption);

            // Add portfolio options - only show portfolios with defined target weights
            this.portfolioData.portfolios.forEach(portfolio => {
                if (portfolio.currentValue && portfolio.currentValue > 0 && portfolio.targetWeight > 0) {
                    const option = document.createElement('option');
                    option.value = portfolio.name;
                    option.textContent = portfolio.name;
                    portfolioSelect.appendChild(option);
                }
            });

            // Set initial selection if none exists
            if (!this.selectedPortfolio && portfolioSelect.options.length > 1) {
                this.selectedPortfolio = portfolioSelect.options[1].value;
                portfolioSelect.value = this.selectedPortfolio;
            }
        }

        showError(message) {
            const container = document.getElementById('portfolio-table-container');
            if (container) {
                container.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="fas fa-exclamation-circle"></i> ${message}
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
                minimumFractionDigits: 1,
                maximumFractionDigits: 1
            }).format(value / 100);
        }

        renderPortfolioTable() {
            if (!this.portfolioData || !this.portfolioData.portfolios || this.portfolioData.portfolios.length === 0) {
                this.showError('No portfolio data available');
                return;
            }

            // Filter out portfolios with current value of 0 AND only include portfolios with defined target weights
            const filteredPortfolios = this.portfolioData.portfolios.filter(portfolio =>
                portfolio.currentValue !== 0 && portfolio.currentValue !== null &&
                portfolio.targetWeight > 0  // Only include portfolios with target allocation defined in builder
            );

            if (filteredPortfolios.length === 0) {
                this.showError('No portfolios with non-zero values available');
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
                            <th>Allocation After Action</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            // Track totals for the summary row
            let totalTargetValue = 0;
            let totalAction = 0;
            let totalValueAfter = 0;

            // First pass: normalize target weights and calculate target values for filtered portfolios
            const totalTargetWeight = filteredPortfolios.reduce((sum, p) => sum + (p.targetWeight || 0), 0);

            // Calculate the new total value after investment
            const newTotalValue = totalCurrentValue + this.investmentAmount;

            filteredPortfolios.forEach(portfolio => {
                // Normalize the target weight as a percentage of the total target weight among filtered portfolios
                const normalizedWeight = totalTargetWeight > 0 ? (portfolio.targetWeight / totalTargetWeight) * 100 : 0;
                // Calculate target value based on NEW total value (current + investment)
                portfolio.targetValue = (normalizedWeight / 100) * newTotalValue;
            });

            // Calculate how much is needed to reach all targets
            let totalNeeded = 0;
            filteredPortfolios.forEach(p => {
                const needed = Math.max(0, p.targetValue - p.currentValue);
                totalNeeded += needed;
            });

            // Determine if we have enough to reach all targets
            const canReachAllTargets = this.investmentAmount >= totalNeeded;

            filteredPortfolios.forEach(portfolio => {
                // Calculate current allocation percentage
                const currentAllocation = totalCurrentValue > 0
                    ? (portfolio.currentValue / totalCurrentValue) * 100
                    : 0;

                // Get target value that was already calculated
                const targetValue = portfolio.targetValue;
                totalTargetValue += targetValue;

                // Calculate action (how much to buy)
                const discrepancy = targetValue - portfolio.currentValue;
                let action = 0;

                if (this.investmentAmount > 0) {
                    if (canReachAllTargets) {
                        // If we can reach all targets, allocate exactly what's needed
                        action = Math.max(0, discrepancy);
                    } else if (discrepancy > 0 && totalNeeded > 0) {
                        // Otherwise, allocate proportionally
                        action = (discrepancy / totalNeeded) * this.investmentAmount;
                    }
                }

                totalAction += action;

                // Calculate value after action
                const valueAfterAction = portfolio.currentValue + action;
                totalValueAfter += valueAfterAction;

                // Store values for second pass
                portfolio.action = action;
                portfolio.valueAfterAction = valueAfterAction;
            });

            // Second pass: Now calculate allocation after action with the correct total
            const finalTotalValue = totalValueAfter;

            filteredPortfolios.forEach(portfolio => {
                // Calculate current allocation percentage
                const currentAllocation = totalCurrentValue > 0
                    ? (portfolio.currentValue / totalCurrentValue) * 100
                    : 0;

                // Calculate allocation after action with the actual total
                const allocationAfterAction = finalTotalValue > 0
                    ? (portfolio.valueAfterAction / finalTotalValue) * 100
                    : 0;

                // Determine action class for styling
                let actionClass = "actions-neutral";
                let actionText = "No action";

                if (portfolio.action > 0) {
                    actionClass = "actions-positive";
                    actionText = `Buy ${this.formatCurrency(portfolio.action)}`;
                }

                // Add row to table
                tableHTML += `
                    <tr>
                        <td>${portfolio.name}</td>
                        <td class="current-value">${this.formatCurrency(portfolio.currentValue)}</td>
                        <td class="allocation-percentage">${this.formatPercentage(currentAllocation)}</td>
                        <td class="target-value">${this.formatPercentage(portfolio.targetWeight || 0)}</td>
                        <td class="target-value">${this.formatCurrency(portfolio.targetValue)}</td>
                        <td class="${actionClass}">${actionText}</td>
                        <td class="value-after">${this.formatCurrency(portfolio.valueAfterAction)}</td>
                        <td class="allocation-after">${this.formatPercentage(allocationAfterAction)}</td>
                    </tr>
                `;
            });

            // Add total row
            tableHTML += `
                    <tr class="total-row">
                        <td><strong>Total</strong></td>
                        <td class="current-value"><strong>${this.formatCurrency(totalCurrentValue)}</strong></td>
                        <td class="allocation-percentage"><strong>100%</strong></td>
                        <td class="target-value"><strong>100%</strong></td>
                        <td class="target-value"><strong>${this.formatCurrency(totalTargetValue)}</strong></td>
                        <td class="actions-positive"><strong>${this.formatCurrency(totalAction)}</strong></td>
                        <td class="value-after"><strong>${this.formatCurrency(totalValueAfter)}</strong></td>
                        <td class="allocation-after"><strong>100%</strong></td>
                    </tr>
                </tbody>
            </table>
            </div>
            `;

            // Update the table container
            const container = document.getElementById('portfolio-table-container');
            if (container) {
                container.innerHTML = tableHTML;
            }
        }

        updateTableCalculations() {
            if (this.portfolioData) {
                this.renderPortfolioTable();
            }
        }

        toggleCategoryExpand(categoryId) {
            if (this.categoriesExpanded.has(categoryId)) {
                this.categoriesExpanded.delete(categoryId);
            } else {
                this.categoriesExpanded.add(categoryId);
            }
            this.renderDetailedView();
        }

        /**
         * Render the detailed view according to the rebalancing actions table plan
         */
        renderDetailedView() {
            const detailedContainer = document.getElementById('detailed-portfolio-container');

            if (!detailedContainer) return;
            if (!this.portfolioData || !this.portfolioData.portfolios) return;

            // Clear the container
            detailedContainer.innerHTML = '';

            // If no portfolio is selected, show a message
            if (!this.selectedPortfolio) {
                detailedContainer.innerHTML = `
                    <div class="alert alert-info mt-4">
                        Please select a portfolio to view its details.
                    </div>
                `;
                return;
            }

            // Find the selected portfolio
            const portfolio = this.portfolioData.portfolios.find(p => p.name === this.selectedPortfolio);
            if (!portfolio) return;

            // Special handling for GME portfolio - add debugging
            if (portfolio.name === "GME") {
                console.log("Processing GME portfolio:", portfolio);
            }

            // Skip portfolios with no current value
            if (!portfolio.currentValue || portfolio.currentValue === 0) {
                detailedContainer.innerHTML = `
                    <div class="alert alert-warning mt-4">
                        No data available for the selected portfolio.
                    </div>
                `;
                return;
            }

            // Skip portfolios with no target weight defined
            if (!portfolio.targetWeight || portfolio.targetWeight === 0) {
                detailedContainer.innerHTML = `
                    <div class="alert alert-warning mt-4">
                        This portfolio has no target allocation defined in the builder. Please define a target allocation first.
                    </div>
                `;
                return;
            }

            // Calculate the specific action amount for this portfolio from the global view
            let portfolioActionAmount = 0;

            if (this.investmentAmount > 0) {
                // Filter out portfolios with current value of 0 AND only include portfolios with defined target weights
                const filteredPortfolios = this.portfolioData.portfolios.filter(p =>
                    p.currentValue !== 0 && p.currentValue !== null &&
                    p.targetWeight > 0  // Only include portfolios with target allocation defined in builder
                );

                // Calculate total current value
                const totalCurrentValue = filteredPortfolios.reduce(
                    (sum, p) => sum + (p.currentValue || 0), 0
                );

                // Calculate target values for all portfolios - normalize target weights first
                const totalTargetWeight = filteredPortfolios.reduce((sum, p) => sum + (p.targetWeight || 0), 0);
                const newTotalValue = totalCurrentValue + this.investmentAmount;

                filteredPortfolios.forEach(p => {
                    // Normalize the target weight as a percentage of the total target weight among filtered portfolios
                    const normalizedWeight = totalTargetWeight > 0 ? (p.targetWeight / totalTargetWeight) * 100 : 0;
                    p.targetValue = (normalizedWeight / 100) * newTotalValue;
                });

                // Calculate how much is needed to reach all targets
                let totalNeeded = 0;
                filteredPortfolios.forEach(p => {
                    const needed = Math.max(0, p.targetValue - p.currentValue);
                    totalNeeded += needed;
                });

                // Determine if we can reach all targets
                const canReachAllTargets = this.investmentAmount >= totalNeeded;

                // Ensure this portfolio has targetValue calculated
                if (!portfolio.targetValue) {
                    const normalizedWeight = totalTargetWeight > 0 ? (portfolio.targetWeight / totalTargetWeight) * 100 : 0;
                    portfolio.targetValue = (normalizedWeight / 100) * newTotalValue;
                }

                const portfolioDiscrepancy = portfolio.targetValue - portfolio.currentValue;
                if (portfolioDiscrepancy > 0) {
                    if (canReachAllTargets) {
                        // If we can reach all targets, allocate exactly what's needed
                        portfolioActionAmount = portfolioDiscrepancy;
                    } else if (totalNeeded > 0) {
                        // Otherwise, allocate proportionally
                        portfolioActionAmount = (portfolioDiscrepancy / totalNeeded) * this.investmentAmount;
                    }
                }
            }

            // Display the action amount for this portfolio at the top of the detailed view
            const investmentInfo = document.createElement('div');
            investmentInfo.className = 'investment-info mb-4';
            investmentInfo.innerHTML = `
                <div class="alert alert-info">
                    <i class="fas fa-info-circle me-2"></i>
                    Portfolio allocation amount: ${this.formatCurrency(portfolioActionAmount)}
                    <span class="text-muted ms-2">(from total investment: ${this.formatCurrency(this.investmentAmount)})</span>
                </div>
            `;
            detailedContainer.appendChild(investmentInfo);

            // Create rebalancing table
            const tableResponsive = document.createElement('div');
            tableResponsive.className = 'table-responsive';

            const table = document.createElement('table');
            table.className = 'table table-hover';

            // Table header
            const thead = document.createElement('thead');
            thead.innerHTML = `
                <tr>
                    <th>Name</th>
                    <th>Current Value</th>
                    <th>Current Allocation</th>
                    <th>Target Allocation</th>
                    <th>Target Value</th>
                    <th>Actions</th>
                    <th>Value After Action</th>
                    <th>Allocation After Action</th>
                </tr>
            `;

            // Table body
            const tbody = document.createElement('tbody');

            // Track totals for portfolio summary
            let totalCurrentValue = portfolio.currentValue || 0;
            let portfolioTargetValue = totalCurrentValue + portfolioActionAmount;
            let totalAction = 0;
            let totalValueAfter = 0;

            // Count total number of positions and positions with user-defined allocations
            let totalPositionsCount = 0;
            let userDefinedAllocationsCount = 0;
            let sumUserDefinedAllocations = 0;

            // First pass: gather position counts and target allocations
            if (portfolio.categories && portfolio.categories.length > 0) {
                portfolio.categories.forEach(category => {
                    if (!category.positions || category.positions.length === 0) return;
                    if (category.name === 'Missing Positions') {
                        const placeholderPosition = category.positions.find(pos => pos.isPlaceholder);
                        if (placeholderPosition) {
                            totalPositionsCount += placeholderPosition.positionsRemaining || 0;
                        }
                    } else {
                        category.positions.forEach(position => {
                            totalPositionsCount++;
                            // Check if position has user-defined allocation
                            if (position.targetAllocation && position.targetAllocation > 0) {
                                userDefinedAllocationsCount++;
                                sumUserDefinedAllocations += position.targetAllocation;
                            }
                        });
                    }
                });
            }

            // Calculate default allocation for positions without user-defined allocations
            let defaultAllocation = 0;
            if (sumUserDefinedAllocations < 100) {
                const remainingAllocation = 100 - sumUserDefinedAllocations;
                const positionsWithoutUserDefinedAllocation = totalPositionsCount - userDefinedAllocationsCount;
                defaultAllocation = positionsWithoutUserDefinedAllocation > 0 ?
                    remainingAllocation / positionsWithoutUserDefinedAllocation : 0;
            }

            // Calculate total positive discrepancy (gap between target and current values)
            let totalPositiveDiscrepancy = 0;

            // Second pass: assign target allocations and calculate discrepancies
            if (portfolio.categories && portfolio.categories.length > 0) {
                portfolio.categories.forEach((category, categoryIndex) => {
                    // Skip categories with no positions
                    if (!category.positions || category.positions.length === 0) return;

                    // Skip "Missing Positions" category temporarily - we'll handle it separately
                    if (category.name === 'Missing Positions') return;

                    // Calculate category metrics
                    let categoryCurrentValue = 0;
                    let categoryTargetAllocation = 0;

                    // Calculate values for each position in the category
                    category.positions.forEach(position => {
                        categoryCurrentValue += (position.currentValue || 0);

                        // Assign target allocation if not already set
                        if (!position.targetAllocation || position.targetAllocation <= 0) {
                            position.targetAllocation = defaultAllocation;
                        }

                        categoryTargetAllocation += position.targetAllocation;

                        // Calculate target value and discrepancy
                        const targetValue = (position.targetAllocation / 100) * portfolioTargetValue;
                        position.calculatedTargetValue = targetValue;

                        const discrepancy = targetValue - (position.currentValue || 0);
                        if (discrepancy > 0) {
                            totalPositiveDiscrepancy += discrepancy;
                        }
                    });

                    // Set category values
                    category.currentValue = categoryCurrentValue;
                    category.targetAllocation = categoryTargetAllocation;
                    category.calculatedTargetValue = (categoryTargetAllocation / 100) * portfolioTargetValue;
                });

                // Handle missing positions if any
                const missingPositionsCategory = portfolio.categories.find(cat =>
                    cat.name === 'Missing Positions' ||
                    cat.positions.some(pos => pos.isPlaceholder));

                // Check if real categories already have 100% allocation
                let realPositionsHave100Percent = false;
                if (portfolio.categories) {
                    const realPositionCategories = portfolio.categories.filter(cat =>
                        cat.name !== 'Missing Positions' &&
                        cat.positions &&
                        cat.positions.length > 0
                    );

                    const totalRealPositionsWeight = realPositionCategories.reduce((sum, cat) => {
                        return sum + cat.targetAllocation;
                    }, 0);

                    // If real positions already have 100% allocation, skip missing positions
                    realPositionsHave100Percent = Math.round(totalRealPositionsWeight) >= 100;

                    // Debugging for GME portfolio
                    if (portfolio.name === "GME") {
                        console.log("GME portfolio calculations:", {
                            realPositionCategories,
                            totalRealPositionsWeight,
                            realPositionsHave100Percent,
                            sumUserDefinedAllocations
                        });
                    }
                }

                // Skip missing positions entirely for GME portfolio
                if (portfolio.name === "GME" && missingPositionsCategory) {
                    console.log("GME portfolio - setting missing positions to 0");
                    missingPositionsCategory.targetAllocation = 0;
                    missingPositionsCategory.calculatedTargetValue = 0;
                }
                // Handle normal case - show missing positions if needed
                else if (missingPositionsCategory && sumUserDefinedAllocations < 100 && !realPositionsHave100Percent) {
                    const placeholderPosition = missingPositionsCategory.positions.find(pos => pos.isPlaceholder);

                    if (placeholderPosition) {
                        const positionsRemaining = placeholderPosition.positionsRemaining || 0;

                        // Assign target allocation to missing positions
                        const missingTargetAllocation = positionsRemaining * defaultAllocation;
                        missingPositionsCategory.targetAllocation = missingTargetAllocation;
                        missingPositionsCategory.calculatedTargetValue = (missingTargetAllocation / 100) * portfolioTargetValue;

                        // Always a positive discrepancy as current value is 0
                        totalPositiveDiscrepancy += missingPositionsCategory.calculatedTargetValue;
                    }
                } else if (missingPositionsCategory) {
                    // If user-defined allocations sum to 100% or real positions have 100%, set missing positions to 0
                    missingPositionsCategory.targetAllocation = 0;
                    missingPositionsCategory.calculatedTargetValue = 0;
                }
            }

            // Third pass: calculate actions and render
            if (portfolio.categories && portfolio.categories.length > 0) {
                portfolio.categories.forEach((category, categoryIndex) => {
                    // Skip categories with no positions
                    if (!category.positions || category.positions.length === 0) return;

                    // Skip "Missing Positions" category temporarily
                    if (category.name === 'Missing Positions') return;

                    const categoryId = `${portfolio.name}-${category.name}-${categoryIndex}`;
                    const isExpanded = this.categoriesExpanded.has(categoryId);

                    // Calculate category metrics for rendering
                    let categoryAction = 0;
                    let categoryValueAfter = 0;

                    // Calculate category percentages
                    const categoryCurrentAllocation = totalCurrentValue > 0
                        ? (category.currentValue / totalCurrentValue) * 100
                        : 0;

                    // Calculate position actions
                    category.positions.forEach(position => {
                        const targetValue = position.calculatedTargetValue;
                        const discrepancy = targetValue - (position.currentValue || 0);
                        let positionAction = 0;

                        if (discrepancy > 0 && portfolioActionAmount > 0 && totalPositiveDiscrepancy > 0) {
                            positionAction = (discrepancy / totalPositiveDiscrepancy) * portfolioActionAmount;
                        }

                        position.action = positionAction;
                        position.valueAfter = (position.currentValue || 0) + positionAction;

                        categoryAction += positionAction;
                        categoryValueAfter += position.valueAfter;
                    });

                    // Determine action class and text for the category
                    let categoryActionClass = "actions-neutral";
                    let categoryActionText = "No action";

                    if (categoryAction > 0) {
                        categoryActionClass = "actions-positive";
                        categoryActionText = `Buy ${this.formatCurrency(categoryAction)}`;
                    }

                    const categoryRow = document.createElement('tr');
                    categoryRow.className = 'table-secondary category-row';
                    categoryRow.style.cursor = 'pointer';

                    // Calculate allocation after action for category
                    const totalValueAfterAllActions = totalCurrentValue + portfolioActionAmount;
                    const categoryAllocationAfterAction = totalValueAfterAllActions > 0
                        ? (categoryValueAfter / totalValueAfterAllActions) * 100
                        : 0;

                    categoryRow.innerHTML = `
                        <td>
                            <i class="fas ${isExpanded ? 'fa-caret-down' : 'fa-caret-right'} me-2"></i>
                            <strong>${category.name}</strong>
                        </td>
                        <td class="current-value">${this.formatCurrency(category.currentValue || 0)}</td>
                        <td>${this.formatPercentage(categoryCurrentAllocation)}</td>
                        <td>${this.formatPercentage(category.targetAllocation)}</td>
                        <td class="target-value">${this.formatCurrency(category.calculatedTargetValue)}</td>
                        <td class="${categoryActionClass}">${categoryActionText}</td>
                        <td class="value-after">${this.formatCurrency(categoryValueAfter)}</td>
                        <td class="allocation-after">${this.formatPercentage(categoryAllocationAfterAction)}</td>
                    `;

                    categoryRow.addEventListener('click', () => {
                        this.toggleCategoryExpand(categoryId);
                    });

                    tbody.appendChild(categoryRow);

                    // Add position rows if category is expanded
                    if (isExpanded) {
                        // Positions in this category
                        category.positions.forEach(position => {
                            // Calculate current allocation
                            const positionCurrentAllocation = totalCurrentValue > 0
                                ? ((position.currentValue || 0) / totalCurrentValue) * 100
                                : 0;

                            // Calculate allocation after action for position
                            const positionAllocationAfterAction = totalValueAfterAllActions > 0
                                ? (position.valueAfter / totalValueAfterAllActions) * 100
                                : 0;

                            // Determine action class and text
                            let actionClass = "actions-neutral";
                            let actionText = "No action";

                            if (position.action > 0) {
                                actionClass = "actions-positive";
                                actionText = `Buy ${this.formatCurrency(position.action)}`;
                            }

                            // Position row - indented to show hierarchy
                            const positionRow = document.createElement('tr');
                            positionRow.className = 'position-row';

                            positionRow.innerHTML = `
                                <td class="position-name">
                                    <span class="ms-4">${position.name}</span>
                                </td>
                                <td class="current-value">${this.formatCurrency(position.currentValue || 0)}</td>
                                <td>${this.formatPercentage(positionCurrentAllocation)}</td>
                                <td>${this.formatPercentage(position.targetAllocation)}</td>
                                <td class="target-value">${this.formatCurrency(position.calculatedTargetValue)}</td>
                                <td class="${actionClass}">${actionText}</td>
                                <td class="value-after">${this.formatCurrency(position.valueAfter)}</td>
                                <td class="allocation-after">${this.formatPercentage(positionAllocationAfterAction)}</td>
                            `;

                            tbody.appendChild(positionRow);

                            // Add to totals
                            totalAction += position.action;
                            totalValueAfter += position.valueAfter;
                        });
                    } else {
                        // If category is collapsed, still add actions to totals
                        totalAction += categoryAction;
                        totalValueAfter += categoryValueAfter;
                    }
                });

                // Handle Missing Positions category separately
                const missingPositionsCategory = portfolio.categories.find(cat =>
                    cat.name === 'Missing Positions' ||
                    cat.positions.some(pos => pos.isPlaceholder));

                // Skip missing positions entirely for GME portfolio
                if (portfolio.name === "GME") {
                    console.log("GME portfolio - not rendering missing positions row");
                }
                // Only show missing positions if they have a non-zero target allocation
                else if (missingPositionsCategory && missingPositionsCategory.targetAllocation > 0) {
                    const placeholderPosition = missingPositionsCategory.positions.find(pos => pos.isPlaceholder);

                    if (placeholderPosition) {
                        const positionsRemaining = placeholderPosition.positionsRemaining || 0;

                        // Calculate action for missing positions
                        let missingAction = 0;
                        if (portfolioActionAmount > 0 && totalPositiveDiscrepancy > 0) {
                            missingAction = (missingPositionsCategory.calculatedTargetValue / totalPositiveDiscrepancy) * portfolioActionAmount;
                        }

                        // Calculate per position investment amount
                        const perPositionAmount = positionsRemaining > 0 ? missingAction / positionsRemaining : 0;

                        // Calculate allocation after action for missing positions
                        const missingAllocationAfterAction = totalValueAfterAllActions > 0
                            ? (missingAction / totalValueAfterAllActions) * 100
                            : 0;

                        // Missing Positions row (special styling)
                        const missingRow = document.createElement('tr');
                        missingRow.className = 'table-warning missing-positions-row';

                        missingRow.innerHTML = `
                            <td>
                                <i class="fas fa-exclamation-triangle me-2"></i>
                                <strong>Missing Positions (${positionsRemaining})</strong>
                            </td>
                            <td class="current-value">${this.formatCurrency(0)}</td>
                            <td>${this.formatPercentage(0)}</td>
                            <td>${this.formatPercentage(missingPositionsCategory.targetAllocation)}</td>
                            <td class="target-value">${this.formatCurrency(missingPositionsCategory.calculatedTargetValue)}</td>
                            <td class="actions-positive">Buy ${this.formatCurrency(perPositionAmount)} × ${positionsRemaining}</td>
                            <td class="value-after">${this.formatCurrency(missingAction)}</td>
                            <td class="allocation-after">${this.formatPercentage(missingAllocationAfterAction)}</td>
                        `;

                        tbody.appendChild(missingRow);

                        // Add to totals
                        totalAction += missingAction;
                        totalValueAfter += missingAction;
                    }
                }
            }

            // Portfolio total row
            const totalRow = document.createElement('tr');
            totalRow.className = 'table-primary fw-bold';

            totalRow.innerHTML = `
                <td>Portfolio Total</td>
                <td class="current-value">${this.formatCurrency(totalCurrentValue)}</td>
                <td>100%</td>
                <td>100%</td>
                <td class="target-value">${this.formatCurrency(portfolioTargetValue)}</td>
                <td>${this.formatCurrency(totalAction)}</td>
                <td class="value-after">${this.formatCurrency(totalValueAfter)}</td>
                <td class="allocation-after">100%</td>
            `;

            tbody.appendChild(totalRow);

            // Assemble table
            table.appendChild(thead);
            table.appendChild(tbody);
            tableResponsive.appendChild(table);

            // Add to container
            detailedContainer.appendChild(tableResponsive);
        }

        renderDetailedChart() {
            const detailedChartContainer = document.getElementById('detailedChart');

            if (!detailedChartContainer) return;
            if (!this.portfolioData || !this.portfolioData.portfolios) return;

            // Filter out portfolios with current value of 0
            const filteredPortfolios = this.portfolioData.portfolios.filter(portfolio =>
                portfolio.currentValue !== 0 && portfolio.currentValue !== null
            );

            // Clear previous chart contents
            detailedChartContainer.innerHTML = '';

            // Prepare data for the detailed chart
            const allCategories = [];

            filteredPortfolios.forEach((portfolio) => {
                if (portfolio.categories && portfolio.categories.length > 0) {
                    portfolio.categories.forEach(category => {
                        // Skip missing positions in chart
                        if (category.name === 'Missing Positions') return;

                        allCategories.push({
                            portfolio: portfolio.name,
                            category: category.name,
                            value: category.currentValue || 0
                        });
                    });
                }
            });

            if (typeof ChartConfig !== 'undefined' && allCategories.length > 0) {
                const labels = allCategories.map(c => `${c.portfolio} - ${c.category}`);
                const values = allCategories.map(c => c.value);
                ChartConfig.createStandardDoughnutChart('detailedChart', labels, values);
            } else {
                detailedChartContainer.innerHTML = `
                    <div class="alert alert-info">
                        No detailed category data available.
                    </div>
                `;
            }
        }
    }

    // Initialize portfolio allocator
    const allocator = new PortfolioAllocator();
});
