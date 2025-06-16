/**
 * frappe_chart_config.js
 * Centralized configuration for all Frappe Chart types in the application
 */

const ChartConfig = {
    /**
     * Standard configuration for all Frappe Charts in the application
     */
    frappeConfig: {
        animate: 1,
        truncateLegends: 1,
        colors: null // Will be set per chart
    },

    /**
     * Creates a donut (pie) chart
     * 
     * @param {string} elementId - ID of the element to render chart in
     * @param {Array<string>} labels - Array of labels
     * @param {Array<number>} values - Array of values
     * @param {Object} options - Additional options
     * @param {string} options.title - Chart title
     * @param {Array<string>} options.colors - Array of colors for each segment
     * @param {Array<number>} options.percentages - Optional array of percentages for display
     * @param {function} options.formatCurrency - Function to format currency values
     * @param {function} options.formatPercentage - Function to format percentage values
     * @param {number} options.height - Chart height in pixels (default: 400)
     */
    createDoughnutChart(elementId, labels, values, options = {}) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.error(`Element with id ${elementId} not found`);
            return null;
        }

        console.log(`Creating donut chart for ${elementId} with ${labels.length} segments`);
        console.log('Values:', values);
        console.log('Labels:', labels);

        // Clear any existing content
        element.innerHTML = '';

        const {
            title = '',
            colors = this.getDefaultColors(labels.length),
            percentages = null,
            formatCurrency = window.formatCurrency || (v => v),
            formatPercentage = window.formatPercentage || (v => v),
            height = 400
        } = options;

        // Calculate total and percentages
        const total = values.reduce((a, b) => a + b, 0);
        const formattedTotal = formatCurrency(total);
        const calculatedPercentages = values.map(v => (v / total) * 100);

        console.log('Total:', total, 'Formatted:', formattedTotal);

        // Create container with specific height
        element.style.height = `${height}px`;
        element.style.position = 'relative';
        element.style.border = '1px solid #ddd'; // Debug border

        try {
            // Create chart data - simplest approach
            const data = {
                labels: labels,
                datasets: [{
                    values: values
                }]
            };

            console.log(`Chart data for ${elementId}:`, data);

            // Create the chart directly with minimal options
            const chart = new frappe.Chart(element, {
                data: data,
                type: 'pie',
                height: height,
                colors: colors,
                maxSlices: 12,
                isNavigable: false,
                animate: 1,
                truncateLegends: 1
            });

            console.log(`Chart created successfully for ${elementId}`);

            // Add total overlay after a short delay
            setTimeout(() => {
                const centerTextElement = document.createElement('div');
                centerTextElement.style.cssText = `
                    position: absolute;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                    font-size: 14px;
                    font-weight: bold;
                    text-align: center;
                    pointer-events: none;
                    background-color: rgba(255, 255, 255, 0.9);
                    padding: 8px 12px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    z-index: 10;
                `;
                centerTextElement.innerHTML = `
                    <div style="margin-bottom: 2px;">${formattedTotal}</div>
                    <div style="font-size: 10px; font-weight: normal; color: #666;">Total</div>
                `;
                element.appendChild(centerTextElement);
            }, 200);

            return chart;

        } catch (error) {
            console.error(`Error creating chart for ${elementId}:`, error);
            element.innerHTML = `
                <div class="has-text-centered p-4">
                    <p class="has-text-danger">Chart Error</p>
                    <p class="is-size-7">${error.message}</p>
                    <p class="is-size-7">Check console for details</p>
                </div>
            `;
            return null;
        }
    },



    /**
     * Updates an existing donut chart with new data
     * 
     * @param {string} elementId - ID of the chart element to update
     * @param {Array<string>} labels - Array of labels
     * @param {Array<number>} values - Array of values
     * @param {Array<string>} colors - Array of colors for each segment
     */
    updateDoughnutChart(elementId, labels, values, colors) {
        // With Frappe Charts, it's easier to recreate the chart
        this.createDoughnutChart(elementId, labels, values, {
            colors: colors,
            height: 400
        });
    },

    /**
     * Creates a horizontal bar chart
     * 
     * @param {string} elementId - ID of the element to render chart in
     * @param {Array<string>} labels - Array of labels
     * @param {Array<number>} values - Array of values
     * @param {Object} options - Additional options
     */
    createBarChart(elementId, labels, values, options = {}) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.error(`Element with id ${elementId} not found`);
            return null;
        }

        // Clear any existing content
        element.innerHTML = '';

        const {
            title = '',
            height = 400,
            color = '#7cd6fd',
            xAxisMode = 'tick',
            yAxisMode = 'span',
            formatValue = (v) => v.toFixed(1) + '%'
        } = options;

        // Create container with specific height
        element.style.height = `${height}px`;

        // Create chart data
        const data = {
            labels: labels,
            datasets: [{
                name: title || 'Values',
                values: values
            }]
        };

        // Create the chart
        const chart = new frappe.Chart(`#${elementId}`, {
            title: title,
            data: data,
            type: 'bar',
            height: height,
            colors: [color],
            barOptions: {
                spaceRatio: 0.5
            },
            axisOptions: {
                xAxisMode: xAxisMode,
                yAxisMode: yAxisMode
            },
            tooltipOptions: {
                formatTooltipY: formatValue
            }
        });

        return chart;
    },

    /**
     * Creates a heatmap chart
     * 
     * @param {string} elementId - ID of the element to render chart in
     * @param {Object} data - Heatmap data with countries, dims, and z matrix
     * @param {Object} options - Additional options
     */
    createHeatmap(elementId, data, options = {}) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.error(`Element with id ${elementId} not found`);
            return null;
        }

        // Clear any existing content
        element.innerHTML = '';

        const {
            title = '',
            height = 400,
            discreteDomains = 1,
            colors = ['#ebedf0', '#c0ddf9', '#73b3f3', '#3886e1', '#17459e']
        } = options;

        // Transform data for Frappe Charts heatmap
        // Frappe expects data in a different format
        const startDate = new Date();
        startDate.setFullYear(startDate.getFullYear() - 1);
        
        // Create dataPoints object
        const dataPoints = {};
        
        // For portfolio heatmap, we'll create a grid view
        // Since Frappe heatmap is date-based, we'll create a custom grid
        element.style.height = `${height}px`;
        element.innerHTML = '<div class="heatmap-custom"></div>';
        
        // Create custom heatmap using divs
        const container = element.querySelector('.heatmap-custom');
        container.style.display = 'grid';
        container.style.gridTemplateColumns = `120px repeat(${data.dims.length}, 1fr)`;
        container.style.gap = '2px';
        container.style.height = '100%';
        container.style.overflow = 'auto';
        
        // Add header row
        container.innerHTML += '<div></div>'; // Empty corner cell
        data.dims.forEach(dim => {
            const cell = document.createElement('div');
            cell.textContent = dim.length > 15 ? dim.substring(0, 15) + '...' : dim;
            cell.style.textAlign = 'center';
            cell.style.fontSize = '12px';
            cell.style.padding = '5px';
            cell.style.fontWeight = 'bold';
            cell.title = dim;
            container.appendChild(cell);
        });
        
        // Add data rows
        data.countries.forEach((country, i) => {
            // Country label
            const label = document.createElement('div');
            label.textContent = country.length > 15 ? country.substring(0, 15) + '...' : country;
            label.style.textAlign = 'right';
            label.style.padding = '5px';
            label.style.fontSize = '12px';
            label.style.fontWeight = 'bold';
            label.title = country;
            container.appendChild(label);
            
            // Data cells
            data.dims.forEach((dim, j) => {
                const value = data.z[i][j];
                const cell = document.createElement('div');
                cell.style.backgroundColor = this.getHeatmapColor(value, colors);
                cell.style.padding = '10px';
                cell.style.textAlign = 'center';
                cell.style.cursor = 'pointer';
                cell.style.transition = 'all 0.2s';
                
                // Add hover effect
                cell.addEventListener('mouseenter', function() {
                    this.style.transform = 'scale(1.1)';
                    this.style.zIndex = '10';
                    this.style.boxShadow = '0 2px 8px rgba(0,0,0,0.2)';
                });
                
                cell.addEventListener('mouseleave', function() {
                    this.style.transform = 'scale(1)';
                    this.style.zIndex = '1';
                    this.style.boxShadow = 'none';
                });
                
                // Add tooltip
                const tooltip = document.createElement('div');
                tooltip.style.position = 'absolute';
                tooltip.style.display = 'none';
                tooltip.style.backgroundColor = 'rgba(0, 0, 0, 0.8)';
                tooltip.style.color = 'white';
                tooltip.style.padding = '8px 12px';
                tooltip.style.borderRadius = '4px';
                tooltip.style.fontSize = '12px';
                tooltip.style.pointerEvents = 'none';
                tooltip.style.zIndex = '1000';
                
                const formatValue = window.formatPercentage || ((v) => v.toFixed(2) + '%');
                tooltip.innerHTML = `
                    <strong>${country} × ${dim}</strong><br>
                    Allocation: ${formatValue(value)}
                `;
                
                document.body.appendChild(tooltip);
                
                cell.addEventListener('mousemove', function(e) {
                    tooltip.style.display = 'block';
                    tooltip.style.left = (e.pageX + 10) + 'px';
                    tooltip.style.top = (e.pageY - 30) + 'px';
                });
                
                cell.addEventListener('mouseleave', function() {
                    tooltip.style.display = 'none';
                });
                
                container.appendChild(cell);
            });
        });
        
        return container;
    },

    /**
     * Get color for heatmap based on value
     */
    getHeatmapColor(value, colors) {
        if (value === 0) return colors[0];
        if (value < 0.5) return colors[1];
        if (value < 1) return colors[2];
        if (value < 2) return colors[3];
        return colors[4];
    },

    /**
     * Generate default colors
     */
    getDefaultColors(count) {
        const baseColors = [
            '#7cd6fd', '#5e64ff', '#743ee2', '#ff5858', '#ffa00a',
            '#28a745', '#98d85b', '#f1c40f', '#e74c3c', '#95a5a6',
            '#3498db', '#9b59b6', '#1abc9c', '#34495e', '#f39c12'
        ];
        
        const colors = [];
        for (let i = 0; i < count; i++) {
            colors.push(baseColors[i % baseColors.length]);
        }
        return colors;
    },

    /**
     * Test function to create a simple chart for debugging
     */
    testChart(elementId) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.error(`Test: Element ${elementId} not found`);
            return;
        }

        console.log('Creating test chart...');
        
        const data = {
            labels: ["Apple", "Orange", "Banana"],
            datasets: [{
                values: [100, 200, 150]
            }]
        };

        try {
            const chart = new frappe.Chart(element, {
                data: data,
                type: 'pie',
                height: 300,
                colors: ['#ff6b6b', '#4ecdc4', '#45b7d1']
            });
            console.log('Test chart created successfully');
            return chart;
        } catch (error) {
            console.error('Test chart error:', error);
            element.innerHTML = `<p>Test Chart Error: ${error.message}</p>`;
        }
    }
}; 