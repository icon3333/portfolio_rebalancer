/**
 * chart_config.js
 * Centralized configuration for all chart types in the application
 */

const ChartConfig = {
    /**
     * Standard configuration for all Plotly charts in the application
     */
    plotlyConfig: {
        responsive: true,
        displayModeBar: false, // Remove the plotly toolbar
        showlegend: false // Remove the legend
    },

    /**
     * Creates a doughnut (pie) chart with a hole in the middle
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
     * @param {boolean} options.showLabels - Whether to show labels (default: true)
     * @param {number} options.holeSize - Size of hole in center (0-1, default: 0.5)
     */
    createDoughnutChart(elementId, labels, values, options = {}) {
        // Set defaults and merge with provided options
        const {
            title = '',
            colors = [],
            percentages = null,
            formatCurrency = window.formatCurrency || (v => v),
            formatPercentage = window.formatPercentage || (v => v),
            height = 400,
            showLabels = true,
            holeSize = 0.5
        } = options;

        const total = values.reduce((a, b) => a + b, 0);
        const formattedTotal = formatCurrency(total);

        // Default hover template uses calculated percentages
        let hoverTemplate = '%{label}: %{value:,.2f} (%{percent})<extra></extra>';
        
        // If percentages are explicitly provided, use custom hover template
        let customText;
        if (percentages && percentages.length === values.length) {
            // Create custom hover text array for each data point
            customText = labels.map((label, i) => {
                return `${label}: ${formatCurrency(values[i])} (${formatPercentage(percentages[i])})`;
            });
        }

        const data = [{
            values: values,
            labels: labels,
            type: 'pie',
            hole: holeSize,
            hoverinfo: 'label+percent+value',
            hovertemplate: hoverTemplate,
            text: customText,
            textinfo: showLabels ? 'label+percent' : 'none',
            textposition: 'inside',
            insidetextorientation: 'radial',
            marker: { colors: colors },
            showlegend: false
        }];

        const layout = {
            title: title,
            height: height,
            margin: { l: 20, r: 20, t: title ? 40 : 20, b: 20 },
            annotations: [{
                font: { size: 14 },
                showarrow: false,
                text: formattedTotal,
                x: 0.5,
                y: 0.5
            }],
            showlegend: false
        };

        return Plotly.newPlot(elementId, data, layout, this.plotlyConfig);
    },

    /**
     * Updates an existing doughnut chart with new data
     * 
     * @param {string} elementId - ID of the chart element to update
     * @param {Array<string>} labels - Array of labels
     * @param {Array<number>} values - Array of values
     * @param {Array<string>} colors - Array of colors for each segment
     */
    updateDoughnutChart(elementId, labels, values, colors) {
        const update = {
            labels: [labels],
            values: [values],
            marker: [{ colors: colors }]
        };
        Plotly.update(elementId, update, {});
    }
}; 