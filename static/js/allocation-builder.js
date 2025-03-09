// Allocation Builder JavaScript - Improved Version
document.addEventListener('DOMContentLoaded', function() {
    // Auto-save debounce function
    function debounce(func, wait = 300) {
      let timeout;
      return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
      };
    }
  
    // Create Vue application
    new Vue({
      el: '#allocation-builder',
      delimiters: ['${', '}'],  // Changed from default {{ }} to avoid collision with Jinja2
      data: {
        budgetData: {
          totalNetWorth: 0,
          alreadyInvested: 0,
          emergencyFund: 0,
          availableToInvest: 0,
          totalInvestableCapital: 0
        },
        rules: {
          maxPerStock: 5,
          maxPerCategory: 25
        },
        portfolios: [],
        availablePortfolios: [],
        portfolioCompanies: {},
        loadingState: false,
        autoSaveIndicator: false,
        sortOptions: {
          column: 'weight',
          direction: 'desc'
        },
        expandedPortfolios: {},
        expandedAllocations: {},
        isEditingWeight: false
      },
      computed: {
        isAllocationValid() {
          const total = this.calculateTotalAllocation();
          return total === 100;
        },
        isAllocationUnder() {
          const total = this.calculateTotalAllocation();
          return total < 100;
        },
        isAllocationOver() {
          const total = this.calculateTotalAllocation();
          return total > 100;
        },
        // Calculate available percentage
        availablePercentage() {
          if (!this.budgetData.totalInvestableCapital) return "0.00";
          return (this.budgetData.availableToInvest / this.budgetData.totalInvestableCapital * 100).toFixed(2);
        }
      },
      mounted() {
        this.loadInitialData();
      },
      methods: {
        // Initial data loading
        async loadInitialData() {
          try {
            this.loadingState = true;
            
            // Load available portfolios
            await this.loadAvailablePortfolios();
            console.log("Available portfolios loaded:", this.availablePortfolios);
            
            // Load saved state if available
            await this.loadSavedState();
            
            // If no portfolios were loaded from saved state, initialize them from available portfolios
            if (!this.portfolios || this.portfolios.length === 0) {
              console.log("No portfolios in saved state, initializing from available portfolios");
              this.portfolios = [];
              
              // For each available portfolio, add it and load its companies
              for (const portfolio of this.availablePortfolios) {
                console.log("Processing portfolio:", portfolio);
                if (portfolio.id) {
                  try {
                    // Add this portfolio with default allocation
                    this.portfolios.push({
                      id: portfolio.id,
                      name: portfolio.name,
                      allocation: 0,
                      positions: []
                    });
                    console.log(`Added portfolio ${portfolio.name} (ID: ${portfolio.id}) to this.portfolios`);
                    
                    // Load companies for this portfolio
                    console.log(`Fetching companies for portfolio ${portfolio.name} (ID: ${portfolio.id})...`);
                    const response = await axios.get(`/portfolio/api/portfolio_companies/${portfolio.id}`);
                    console.log(`Received company data for portfolio ${portfolio.name}:`, response.data);
                    
                    if (response.data && Array.isArray(response.data)) {
                      // Store companies in portfolioCompanies
                      Vue.set(this.portfolioCompanies, portfolio.id, response.data);
                      console.log(`Stored ${response.data.length} companies for portfolio ${portfolio.name}`);
                    } else {
                      // Initialize with empty array if no companies
                      Vue.set(this.portfolioCompanies, portfolio.id, []);
                      console.log(`No companies found for portfolio ${portfolio.name}, initialized with empty array`);
                    }
                  } catch (error) {
                    console.error(`Error loading companies for portfolio ${portfolio.id}:`, error);
                    // Initialize with empty array on error
                    Vue.set(this.portfolioCompanies, portfolio.id, []);
                  }
                }
              }
              console.log("Final portfolios list:", this.portfolios);
              console.log("Final portfolioCompanies:", this.portfolioCompanies);
              
              // Set default allocations
              if (this.portfolios.length > 0) {
                const evenAllocation = (100 / this.portfolios.length).toFixed(2);
                this.portfolios.forEach(p => {
                  p.allocation = parseFloat(evenAllocation);
                });
              }
              
              // Initialize remaining properties for each portfolio
              for (const portfolio of this.portfolios) {
                // Calculate minimum positions needed
                this.calculateMinimumPositions(portfolio);
                // Add placeholder positions if needed
                this.ensureMinimumPositions(portfolio);
              }
            }
            
            // Calculate available to invest
            this.calculateAvailableToInvest();
            
            // Calculate total investable capital
            this.calculateTotalInvestableCapital();
            
            this.loadingState = false;
          } catch (error) {
            console.error('Error loading initial data:', error);
            portfolioManager.showNotification('Failed to load initial data. Please refresh the page.', 'is-danger');
            this.loadingState = false;
          }
        },
        
        // Load saved state from the server
        async loadSavedState() {
          try {
            const response = await axios.get('/portfolio/api/state?page=build');
            console.log('Loaded saved state:', response.data);
            
            if (response.data && response.data.budgetData) {
              this.budgetData = JSON.parse(response.data.budgetData);
              // Ensure we have all required properties
              if (!this.budgetData.hasOwnProperty('totalNetWorth')) {
                this.budgetData.totalNetWorth = 
                  (parseFloat(this.budgetData.totalInvestableCapital) || 0) + 
                  (parseFloat(this.budgetData.emergencyFund) || 0);
              }
              
              // Recalculate totalInvestableCapital and availableToInvest to ensure consistency
              this.calculateTotalInvestableCapital();
              this.calculateAvailableToInvest();
            }
            
            if (response.data && response.data.rules) {
              this.rules = JSON.parse(response.data.rules);
            }
            
            // Create a map of available portfolio IDs and names
            const availablePortfolioMap = {};
            this.availablePortfolios.forEach(p => {
              if (p.id) {
                availablePortfolioMap[p.id] = p.name;
              }
            });
            console.log('Available portfolio map:', availablePortfolioMap);
            
            // Temporary array to store portfolios from saved state
            let savedPortfolios = [];
            let savedPortfolioIds = new Set();
            
            if (response.data && response.data.portfolios) {
              savedPortfolios = JSON.parse(response.data.portfolios);
              
              // Filter out portfolios without an ID
              savedPortfolios = savedPortfolios.filter(p => p.id);
              
              // Track which portfolio IDs we have from saved state
              savedPortfolioIds = new Set(savedPortfolios.map(p => p.id));
              console.log('Saved portfolio IDs:', Array.from(savedPortfolioIds));
            }
            
            // Initialize this.portfolios with saved portfolios
            this.portfolios = savedPortfolios;
            
            // Add any missing portfolios from availablePortfolios
            for (const portfolio of this.availablePortfolios) {
              if (portfolio.id && !savedPortfolioIds.has(portfolio.id)) {
                console.log(`Adding missing portfolio to state: ${portfolio.name} (ID: ${portfolio.id})`);
                this.portfolios.push({
                  id: portfolio.id,
                  name: portfolio.name,
                  allocation: 0,
                  positions: []
                });
              }
            }
            
            console.log('Final portfolio list after merging saved state:', this.portfolios);
            
            // Load companies for each portfolio and ensure positions exist
            const portfoliosWithCompanies = [];
            for (const portfolio of this.portfolios) {
              if (portfolio.id) {
                // Initialize positions array if missing
                if (!portfolio.positions) {
                  portfolio.positions = [];
                }
                
                // Load companies and create positions as needed
                await this.loadPortfolioCompanies(portfolio.id);
                
                // Only keep portfolios that have companies
                if (this.portfolioCompanies[portfolio.id] && this.portfolioCompanies[portfolio.id].length > 0) {
                  portfoliosWithCompanies.push(portfolio);
                  // Calculate minimum positions needed
                  this.calculateMinimumPositions(portfolio);
                  // Add placeholder positions if needed
                  this.ensureMinimumPositions(portfolio);
                } else {
                  console.log(`Skipping portfolio ${portfolio.name} (ID: ${portfolio.id}) because it has no companies`);
                }
              }
            }
            
            // Replace the portfolios array with only those that have companies
            this.portfolios = portfoliosWithCompanies;
            console.log('Final filtered portfolio list (only with companies):', this.portfolios);
            
            if (response.data && response.data.expandedPortfolios) {
              this.expandedPortfolios = JSON.parse(response.data.expandedPortfolios);
            }
            
            if (response.data && response.data.expandedAllocations) {
              this.expandedAllocations = JSON.parse(response.data.expandedAllocations);
            }
            
            if (response.data && response.data.sortOptions) {
              this.sortOptions = JSON.parse(response.data.sortOptions);
            }
          } catch (error) {
            console.error('Error loading saved state:', error);
            // If error loading saved state, start with default values
          }
        },
        
        // Load available portfolios
        async loadAvailablePortfolios() {
          try {
            // Add has_companies=true to only get portfolios that have companies with shares
            const response = await axios.get('/portfolio/api/portfolios?include_ids=true&has_companies=true');
            this.availablePortfolios = response.data;
            console.log('Loaded portfolios with companies:', this.availablePortfolios);
          } catch (error) {
            console.error('Error loading portfolios:', error);
            portfolioManager.showNotification('Failed to load portfolios', 'is-danger');
          }
        },
        
        // Load companies for a specific portfolio
        async loadPortfolioCompanies(portfolioId) {
          try {
            const response = await axios.get(`/portfolio/api/portfolio_companies/${portfolioId}`);
            const companies = response.data;
            console.log(`Loaded ${companies.length} companies for portfolio ${portfolioId}:`, companies);
            
            // Store in portfolioCompanies map
            Vue.set(this.portfolioCompanies, portfolioId, companies);
            
            // Find the portfolio in our portfolios array
            const portfolioIndex = this.portfolios.findIndex(p => p.id === portfolioId);
            if (portfolioIndex !== -1) {
              const portfolio = this.portfolios[portfolioIndex];
              
              // Create positions for companies if they don't already exist
              if (companies && companies.length > 0) {
                // Get existing position company IDs to avoid duplicates
                const existingCompanyIds = new Set(portfolio.positions
                  .filter(p => !p.isPlaceholder && p.companyId)
                  .map(p => p.companyId));
                
                // Add positions for companies that don't already have positions
                for (const company of companies) {
                  if (!existingCompanyIds.has(company.id)) {
                    console.log(`Creating position for company ${company.name} (ID: ${company.id})`);
                    portfolio.positions.push({
                      companyId: company.id,
                      companyName: company.name,
                      weight: 0, // Will be calculated later
                      isPlaceholder: false
                    });
                  }
                }
                
                // Apply consistent weight calculation
                if (portfolio.evenSplit) {
                  this.updatePositionAllocations(portfolioIndex);
                }
              }
            }
          } catch (error) {
            console.error(`Error loading companies for portfolio ${portfolioId}:`, error);
            portfolioManager.showNotification(`Failed to load companies for portfolio`, 'is-danger');
          }
        },
        
        // Budget calculations
        calculateAvailableToInvest() {
          const totalInvestableCapital = parseFloat(this.budgetData.totalInvestableCapital) || 0;
          const alreadyInvested = parseFloat(this.budgetData.alreadyInvested) || 0;
          
          this.budgetData.availableToInvest = Math.max(0, totalInvestableCapital - alreadyInvested);
        },
        
        calculateTotalInvestableCapital() {
          const totalNetWorth = parseFloat(this.budgetData.totalNetWorth) || 0;
          const emergencyFund = parseFloat(this.budgetData.emergencyFund) || 0;
          
          // Total Investable Capital is now derived from Total Net Worth minus Emergency Fund
          this.budgetData.totalInvestableCapital = Math.max(0, totalNetWorth - emergencyFund);
        },
        
        updateBudgetData() {
          // First calculate Total Investable Capital from Total Net Worth and Emergency Fund
          this.calculateTotalInvestableCapital();
          
          // Then calculate Available to Invest
          this.calculateAvailableToInvest();
          
          // Trigger auto-save
          this.debouncedSave();
        },
        
        // Portfolio management
        togglePortfolioExpand(index) {
          const portfolioId = this.portfolios[index].id;
          if (!this.expandedPortfolios[portfolioId]) {
            Vue.set(this.expandedPortfolios, portfolioId, true);
          } else {
            Vue.set(this.expandedPortfolios, portfolioId, !this.expandedPortfolios[portfolioId]);
          }
          // Save expanded state
          this.debouncedSave();
        },
        
        isPortfolioExpanded(index) {
          const portfolioId = this.portfolios[index].id;
          return this.expandedPortfolios[portfolioId] === true;
        },
        
        // Calculate minimum positions needed
        calculateMinimumPositions(portfolio) {
          // Get portfolio percentage of total account
          const portfolioPercentage = portfolio.allocation; 
          
          // Get maximum percent per stock
          const maxPerStock = this.rules.maxPerStock;
          
          // Calculate minimum positions needed: Z = X% ÷ Y%
          // Round up and apply 2 decimal precision
          let minPositions = Math.ceil(portfolioPercentage / maxPerStock * 100) / 100;
          
          // Ensure at least 1 position
          minPositions = Math.max(1, minPositions);
          
          // Update portfolio
          portfolio.minPositions = minPositions;
          
          return minPositions;
        },
        
        // Ensure portfolio has minimum number of positions
        ensureMinimumPositions(portfolio) {
          if (!portfolio.positions) {
            portfolio.positions = [];
          }
          
          // Calculate min positions if not already set
          if (!portfolio.minPositions) {
            this.calculateMinimumPositions(portfolio);
          }
          
          // Just use the calculated minimum positions, rounded up to nearest integer
          const minPositions = Math.ceil(portfolio.minPositions);
          
          // First, filter out all placeholder positions to avoid duplicates
          portfolio.positions = portfolio.positions.filter(p => !p.isPlaceholder);
          
          // Count real positions
          const realPositionCount = portfolio.positions.length;
          
          // If we already have enough real positions, we don't need placeholders
          if (realPositionCount >= minPositions) {
            return;
          }
          
          // Calculate actual number of positions remaining
          const positionsRemaining = minPositions - realPositionCount;
          
          // For placeholder position, just add it with basic properties - weight will be calculated consistently
          portfolio.positions.push({
            companyId: null,
            companyName: `${positionsRemaining}x positions remaining`,
            weight: 0, // This will be calculated correctly by applyConsistentWeightCalculation
            isPlaceholder: true
          });
          
          // Apply consistent weight calculation to ensure this portfolio has correct weights
          // Note: We need to find the index of this portfolio in the portfolios array
          const portfolioIndex = this.portfolios.findIndex(p => p === portfolio);
          if (portfolioIndex !== -1 && portfolio.evenSplit) {
            this.applyConsistentWeightCalculation();
          }
        },
                
        // Update position details when company is selected
        updatePositionDetails(portfolioIndex, positionIndex) {
          const portfolio = this.portfolios[portfolioIndex];
          const position = portfolio.positions[positionIndex];
          const companyId = position.companyId;
          
          if (companyId) {
            const company = this.portfolioCompanies[portfolio.id].find(c => c.id === companyId);
            if (company) {
              position.companyName = company.name;
            }
          }
          
          // Auto-save
          this.debouncedSave();
        },
        
        // Update position allocations when weights change
        updatePositionAllocations(portfolioIndex) {
          const portfolio = this.portfolios[portfolioIndex];
          
          // If there are no positions, nothing to update
          if (portfolio.positions.length === 0) {
            return;
          }
          
          // If even split is enabled, use our consistent calculation method
          if (portfolio.evenSplit) {
            this.applyConsistentWeightCalculation();
          }
          
          // Ensure total weight doesn't exceed 100%
          let totalWeight = this.calculateTotalWeight(portfolioIndex);
          if (totalWeight > 100) {
            const scaleFactor = 100 / totalWeight;
            
            portfolio.positions.forEach(position => {
              position.weight = parseFloat((position.weight * scaleFactor).toFixed(2));
            });
            
            // After scaling, reapply consistent weight calculation for placeholders
            if (portfolio.evenSplit) {
              this.applyConsistentWeightCalculation();
            }
          }
          
          // Auto-save
          this.debouncedSave();
        },
        
        // Apply consistent weight calculation across all portfolios
        applyConsistentWeightCalculation() {
          // Apply to each portfolio
          this.portfolios.forEach((portfolio, portfolioIndex) => {
            if (!portfolio.evenSplit || !portfolio.positions || portfolio.positions.length === 0) {
              return; // Skip if not in even split mode or no positions
            }
            
            // Calculate minimum positions required (just use the calculated value)
            const minPositions = Math.ceil(portfolio.minPositions || 1);
            
            // Get real positions (non-placeholder)
            const realPositions = portfolio.positions.filter(p => !p.isPlaceholder);
            const realPositionCount = realPositions.length;
            
            // Calculate weight per position based on minimum required positions
            const weightPerPosition = parseFloat((100 / minPositions).toFixed(2));
            
            // Set weight for real positions
            realPositions.forEach(position => {
              position.weight = weightPerPosition;
            });
            
            // Check if we need to add or update a placeholder position
            if (realPositionCount < minPositions) {
              // Calculate how many positions remain
              const positionsRemaining = minPositions - realPositionCount;
              
              // Look for existing placeholder
              let placeholder = portfolio.positions.find(p => p.isPlaceholder);
              
              // If no placeholder exists, create one
              if (!placeholder) {
                placeholder = {
                  companyId: null,
                  companyName: `${positionsRemaining}x positions remaining`,
                  weight: 0,
                  isPlaceholder: true
                };
                portfolio.positions.push(placeholder);
              }
              
              // Update placeholder name and weight
              placeholder.companyName = `${positionsRemaining}x positions remaining`;
              placeholder.weight = parseFloat((weightPerPosition * positionsRemaining).toFixed(2));
            } else {
              // No placeholders needed if we have enough real positions
              portfolio.positions = portfolio.positions.filter(p => !p.isPlaceholder);
              
              // Ensure total weight is exactly 100%
              let totalWeight = realPositions.reduce((sum, pos) => sum + pos.weight, 0);
              if (Math.abs(totalWeight - 100) > 0.01 && realPositionCount > 0) {
                // Add any remainder to the first position
                const diff = parseFloat((100 - totalWeight).toFixed(2));
                realPositions[0].weight = parseFloat((realPositions[0].weight + diff).toFixed(2));
              }
            }
          });
        },
        
        // Recalculate weights for even distribution - delegate to applyConsistentWeightCalculation
        recalculateEvenWeights(portfolioIndex) {
          this.applyConsistentWeightCalculation();
        },
        
        // Handle manual weight input
        updateManualWeight(portfolioIndex, positionIndex, value) {
          // Set editing flag to prevent immediate sorting
          this.isEditingWeight = true;
          
          // Parse the input value, removing any % sign if present
          let numValue = parseFloat(value.replace('%', ''));
          
          if (!isNaN(numValue)) {
            // Round to 2 decimal places
            numValue = parseFloat(numValue.toFixed(2));
            
            // Set the new weight
            this.portfolios[portfolioIndex].positions[positionIndex].weight = numValue;
            
            // Update other position weights if this is not a placeholder
            if (!this.portfolios[portfolioIndex].positions[positionIndex].isPlaceholder) {
              // Only trigger re-distribution if not even split
              if (!this.portfolios[portfolioIndex].evenSplit) {
                this.updatePositionAllocations(portfolioIndex);
              }
            }
            
            // Trigger auto-save
            this.debouncedSave();
          }
          
          // Reset editing flag after a short delay
          setTimeout(() => {
            this.isEditingWeight = false;
          }, 1000);
        },
        
        // Check if position weight exceeds maximum
        isWeightExceeded(portfolioIndex, positionIndex) {
          const portfolio = this.portfolios[portfolioIndex];
          const position = portfolio.positions[positionIndex];
          
          // Calculate maximum allowed weight
          const maxWeight = 100 / Math.max(1, Math.ceil(portfolio.minPositions));
          
          return position.weight > maxWeight;
        },
        
        // Update portfolio allocations
        updateAllocations() {
          // Ensure total allocation doesn't exceed 100%
          let totalAllocation = this.calculateTotalAllocation();
          
          if (totalAllocation > 100) {
            const scaleFactor = 100 / totalAllocation;
            
            this.portfolios.forEach(portfolio => {
              portfolio.allocation = parseFloat((portfolio.allocation * scaleFactor).toFixed(2));
            });
          }
          
          // Auto-save
          this.debouncedSave();
        },
        
        // Calculate total weight for a portfolio
        calculateTotalWeight(portfolioIndex) {
          const portfolio = this.portfolios[portfolioIndex];
          return portfolio.positions.reduce((total, position) => total + parseFloat(position.weight || 0), 0);
        },
        
        // Calculate total allocation percentage
        calculateTotalAllocation() {
          return this.portfolios.reduce((total, portfolio) => total + parseFloat(portfolio.allocation || 0), 0);
        },
        
        // Calculate allocation amount based on percentage
        calculateAllocationAmount(allocationPercentage) {
          const totalInvestableCapital = parseFloat(this.budgetData.totalInvestableCapital) || 0;
          return totalInvestableCapital * (parseFloat(allocationPercentage) / 100);
        },
        
        // Calculate position amount
        calculatePositionAmount(portfolioIndex, positionIndex) {
          const portfolio = this.portfolios[portfolioIndex];
          const position = portfolio.positions[positionIndex];
          const portfolioAmount = this.calculateAllocationAmount(portfolio.allocation);
          
          // Simply use the position's weight percentage to calculate the amount
          // The weights are already set correctly by applyConsistentWeightCalculation
          // when evenSplit is enabled
          return portfolioAmount * (parseFloat(position.weight || 0) / 100);
        },
        
        // Calculate total allocated amount
        calculateTotalAllocatedAmount() {
          const totalInvestableCapital = parseFloat(this.budgetData.totalInvestableCapital) || 0;
          const totalAllocationPercentage = this.calculateTotalAllocation() / 100;
          
          return totalInvestableCapital * totalAllocationPercentage;
        },
        
        // Calculate unallocated amount
        calculateUnallocatedAmount() {
          const totalInvestableCapital = parseFloat(this.budgetData.totalInvestableCapital) || 0;
          const allocatedAmount = this.calculateTotalAllocatedAmount();
          
          return totalInvestableCapital - allocatedAmount;
        },
        
        // Calculate total number of positions
        calculateTotalPositions() {
          return this.portfolios.reduce((total, portfolio) => {
            // Don't count placeholder positions
            return total + portfolio.positions.filter(p => !p.isPlaceholder).length;
          }, 0);
        },
        
        // Get portfolio name by ID
        getPortfolioName(portfolioId) {
          if (!portfolioId) return 'Unselected Portfolio';
          
          const portfolio = this.availablePortfolios.find(p => p.id === portfolioId);
          return portfolio ? portfolio.name : 'Unknown Portfolio';
        },
        
        // Format currency using utility function
        formatCurrency(amount) {
          return portfolioManager.formatCurrency(amount);
        },
        
        // Format number with thousand separators
        formatNumber(value) {
          if (value === null || value === undefined) return '0';
          return parseFloat(value).toLocaleString('en-US', {maximumFractionDigits: 2, minimumFractionDigits: 2});
        },
        
        // Format percentage with 2 decimal places
        formatPercentage(value) {
          if (value === null || value === undefined) return '0.00%';
          return `${parseFloat(value).toFixed(2)}%`;
        },
        
        // Sort table by column
        sortBy(column) {
          // Don't change sort immediately when editing weights
          if (this.isEditingWeight) {
            return;
          }
          
          if (this.sortOptions.column === column) {
            // Toggle direction if same column clicked
            this.sortOptions.direction = this.sortOptions.direction === 'asc' ? 'desc' : 'asc';
          } else {
            // Set new column with default direction
            this.sortOptions.column = column;
            this.sortOptions.direction = column === 'name' ? 'asc' : 'desc';
          }
          
          // Save sort preference
          this.debouncedSave();
        },
        
        // Sort positions by selected column
        sortedPositions(positions) {
          if (!positions || positions.length === 0) return [];
          
          // Separate placeholder positions from real positions
          const placeholders = positions.filter(p => p.isPlaceholder);
          const realPositions = positions.filter(p => !p.isPlaceholder);
          
          // Sort only the real positions by selected column
          realPositions.sort((a, b) => {
            let valueA, valueB;
            
            // Get values based on sort column
            switch (this.sortOptions.column) {
              case 'name':
                valueA = a.companyName || '';
                valueB = b.companyName || '';
                break;
              case 'weight':
                valueA = parseFloat(a.weight || 0);
                valueB = parseFloat(b.weight || 0);
                break;
              case 'amount':
                // We'd need portfolio index and position index for this
                // As a fallback, use weight
                valueA = parseFloat(a.weight || 0);
                valueB = parseFloat(b.weight || 0);
                break;
              default:
                valueA = a[this.sortOptions.column] || 0;
                valueB = b[this.sortOptions.column] || 0;
            }
            
            // Sort ascending or descending
            if (this.sortOptions.direction === 'asc') {
              return valueA > valueB ? 1 : valueA < valueB ? -1 : 0;
            } else {
              return valueA < valueB ? 1 : valueA > valueB ? -1 : 0;
            }
          });
          
          // Return real positions followed by placeholders
          return [...realPositions, ...placeholders];
        },
        
        // Group positions by weight
        groupPositionsByWeight(positions, portfolio) {
          // Don't include placeholder positions
          const realPositions = positions.filter(p => !p.isPlaceholder);
          
          const weightGroups = {};
          
          // Group positions by their weights
          realPositions.forEach(position => {
            const weight = parseFloat(position.weight).toFixed(2);
            
            if (!weightGroups[weight]) {
              weightGroups[weight] = {
                weight: parseFloat(weight),
                positions: [],
                count: 0
              };
            }
            
            weightGroups[weight].positions.push(position);
            weightGroups[weight].count++;
          });
          
          // Convert to array for rendering
          const result = [];
          
          for (const weight in weightGroups) {
            const group = weightGroups[weight];
            
            if (group.count === 1) {
              // Single position, display normally
              const position = group.positions[0];
              const company = this.portfolioCompanies[portfolio.id]?.find(c => c.id === position.companyId);
              
              result.push({
                companyName: company ? company.name : 'Unknown',
                weight: group.weight,
                count: 1
              });
            } else {
              // Multiple positions with same weight, group them
              result.push({
                companyName: `${group.count}x positions with equal weight`,
                weight: group.weight,
                count: group.count
              });
            }
          }
          
          // Sort by weight (descending)
          return result.sort((a, b) => b.weight - a.weight);
        },
        
        // Toggle allocation row expansion
        toggleAllocationExpand(portfolioId) {
          if (!this.expandedAllocations[portfolioId]) {
            Vue.set(this.expandedAllocations, portfolioId, true);
          } else {
            Vue.set(this.expandedAllocations, portfolioId, !this.expandedAllocations[portfolioId]);
          }
          
          // Save expanded state
          this.debouncedSave();
        },
        
        isAllocationExpanded(portfolioId) {
          return this.expandedAllocations[portfolioId] === true;
        },
        
        // Save allocation state
        async saveAllocation() {
          try {
            this.loadingState = true;
            this.autoSaveIndicator = true;
            
            const data = {
              page: 'build',
              budgetData: JSON.stringify(this.budgetData),
              rules: JSON.stringify(this.rules),
              portfolios: JSON.stringify(this.portfolios),
              expandedPortfolios: JSON.stringify(this.expandedPortfolios),
              expandedAllocations: JSON.stringify(this.expandedAllocations),
              sortOptions: JSON.stringify(this.sortOptions)
            };
            
            await axios.post('/portfolio/api/state', data);
            
            setTimeout(() => {
              this.autoSaveIndicator = false;
            }, 1000);
            
            this.loadingState = false;
          } catch (error) {
            console.error('Error saving allocation:', error);
            portfolioManager.showNotification('Failed to save allocation', 'is-danger');
            this.autoSaveIndicator = false;
            this.loadingState = false;
          }
        }
      },
      // Create debounced save method
      created() {
        this.debouncedSave = debounce(this.saveAllocation, 500);
        // Initialize editing flag
        this.isEditingWeight = false;
      },
      // Watch for changes to trigger auto-save
      watch: {
        budgetData: {
          handler() {
            this.debouncedSave();
          },
          deep: true
        },
        rules: {
          handler() {
            // Recalculate minimum positions when rules change
            this.portfolios.forEach((portfolio, index) => {
              this.calculateMinimumPositions(portfolio);
              this.ensureMinimumPositions(portfolio);
            });
            this.debouncedSave();
          },
          deep: true
        },
        portfolios: {
          handler() {
            this.debouncedSave();
          },
          deep: true
        }
      }
    });
  });