/**
 * ChartConfig for ApexCharts
 *
 * This configuration object provides a centralized way to create and manage
 * ApexCharts instances with consistent styling and options.
 */
const ChartConfig = {
    // Default options for all charts
    defaultOptions: {
        chart: {
            fontFamily: '"Helvetica Neue", Arial, sans-serif',
            toolbar: {
                show: false
            },
            zoom: {
                enabled: false
            }
        },
        grid: {
            show: false
        },
        dataLabels: {
            enabled: true,
            style: {
                fontSize: '12px',
                fontWeight: 'bold'
            }
        },
        tooltip: {
            theme: 'light',
            style: {
                fontSize: '12px'
            }
        },
        legend: {
            show: false // Hiding legend by default as requested
        },
        responsive: [{
            breakpoint: 480,
            options: {
                chart: {
                    width: '100%'
                },
                legend: {
                    show: false // Ensure legend is hidden on small screens too
                }
            }
        }]
    },

    // Chart instances cache
    chartInstances: {},

    /**
     * Creates a doughnut chart
     *
     * @param {string} elementId - ID of the element to render chart in
     * @param {Array<string>} labels - Array of labels
     * @param {Array<number>} values - Array of values
     * @param {Object} options - Additional chart options
     */
    createDoughnutChart(elementId, labels, values, options = {}) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.error(`Element with id ${elementId} not found`);
            return null;
        }
        element.innerHTML = ''; // Clear previous content

        const {
            title = '',
            colors = this.generateColors(labels.length),
            percentages,
            formatCurrency = v => `€${Math.round(v).toLocaleString()}`,
            formatPercentage = v => `${v.toFixed(1)}%`,
            height = 400,
            showTotal = true
        } = options;

        // Validate and clean the input values
        const cleanedValues = values.map(v => {
            const num = parseFloat(v);
            return isNaN(num) ? 0 : num;
        });
        
        const total = cleanedValues.reduce((a, b) => a + b, 0);
        const calculatedPercentages = cleanedValues.map(v => total > 0 ? (v / total) * 100 : 0);
        const finalPercentages = percentages || calculatedPercentages;

        // Ensure we have valid percentages for all labels
        const enhancedLabels = labels.map((label, i) => {
            const percentage = finalPercentages[i];
            if (percentage !== undefined && !isNaN(percentage)) {
                return `${label} (${formatPercentage(percentage)})`;
            } else {
                return label;
            }
        });

        // Create a simpler chart configuration to avoid the error
        const chartOptions = {
            series: cleanedValues,
            labels: labels, // Use simple labels without percentages for now
            chart: {
                type: 'donut',
                height: height,
                fontFamily: '"Helvetica Neue", Arial, sans-serif',
                toolbar: {
                    show: false
                },
                zoom: {
                    enabled: false
                }
            },
            colors: colors,
            plotOptions: {
                pie: {
                    donut: {
                        size: '65%',
                        labels: {
                            show: showTotal,
                            name: {
                                show: true,
                                fontSize: '14px',
                                fontWeight: 400,
                                color: '#666',
                                offsetY: -10
                            },
                            value: {
                                show: true,
                                fontSize: '24px',
                                fontWeight: 700,
                                color: '#111',
                                offsetY: 10,
                                formatter: function (val) {
                                    return formatCurrency(parseFloat(val) || 0);
                                }
                            },
                            total: {
                                show: true,
                                showAlways: true,
                                label: 'Total',
                                fontSize: '14px',
                                fontWeight: 400,
                                color: '#666',
                                formatter: function (w) {
                                    return formatCurrency(total);
                                }
                            }
                        }
                    }
                }
            },
            dataLabels: {
                enabled: true,
                style: {
                    fontSize: '12px',
                    fontWeight: 'bold'
                },
                formatter: function(val, opts) {
                    const value = cleanedValues[opts.seriesIndex];
                    return formatCurrency(value);
                }
            },
            tooltip: {
                enabled: true,
                theme: 'light',
                style: {
                    fontSize: '12px'
                },
                y: {
                    formatter: function(value) {
                        return formatCurrency(value);
                    },
                    title: {
                        formatter: function(seriesName) {
                            return seriesName;
                        }
                    }
                }
            },
            legend: {
                show: false
            },
            responsive: [{
                breakpoint: 480,
                options: {
                    chart: {
                        width: '100%'
                    }
                }
            }]
        };
        
        if (title) {
            chartOptions.title = {
                text: title,
                align: 'center',
                style: {
                    fontSize: '18px',
                    fontWeight: 600,
                    color: '#333'
                }
            };
        }

        try {
            // Debug logging
            console.log(`Creating chart for ${elementId} with:`, {
                series: cleanedValues,
                labels: labels,
                colorsLength: colors.length,
                element: element,
                elementDimensions: {
                    width: element.offsetWidth,
                    height: element.offsetHeight
                }
            });
            
            // Ensure element has dimensions
            if (element.offsetWidth === 0 || element.offsetHeight === 0) {
                console.warn(`Element ${elementId} has no dimensions. Setting default size.`);
                element.style.width = '100%';
                element.style.height = height + 'px';
                element.style.display = 'block';
            }
            
            const chart = new ApexCharts(element, chartOptions);
            chart.render();
            this.chartInstances[elementId] = chart;
            return chart;
        } catch (error) {
            console.error(`Error creating doughnut chart for ${elementId}:`, error);
            console.error('Chart options were:', chartOptions);
            element.innerHTML = `<div style="text-align: center; padding: 20px;"><p style="color: #dc3545;">Chart Error</p><p style="font-size: 12px;">${error.message}</p></div>`;
            return null;
        }
    },

    /**
     * Updates an existing doughnut chart
     */
    updateDoughnutChart(elementId, labels, values, colors) {
        const chart = this.chartInstances[elementId];
        if (chart) {
            const total = values.reduce((a, b) => a + b, 0);
            const percentages = values.map(v => total > 0 ? (v / total) * 100 : 0);
            const formatPercentage = v => `${v.toFixed(1)}%`;
            const enhancedLabels = labels.map((label, i) => `${label} (${formatPercentage(percentages[i])})`);

            chart.updateOptions({
                labels: enhancedLabels,
                colors: colors || this.generateColors(labels.length)
            });
            chart.updateSeries(values);
        } else {
            this.createDoughnutChart(elementId, labels, values, { colors });
        }
    },

    /**
     * Creates a heatmap chart using ApexCharts
     *
     * @param {string} elementId - ID of the element to render chart in
     * @param {Object} data - Heatmap data with countries, dims, and z matrix
     * @param {Object} options - Additional chart options
     */
    createHeatmap(elementId, data, options = {}) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.error(`Element with id ${elementId} not found`);
            return null;
        }
        element.innerHTML = ''; // Clear previous content

        const {
            title = '',
            height = 400,
            colors = ['#ebedf0', '#c0ddf9', '#73b3f3', '#3886e1', '#17459e']
        } = options;

        // Prepare data for ApexCharts heatmap format
        const series = data.countries.map((country, countryIndex) => ({
            name: country,
            data: data.dims.map((dim, dimIndex) => ({
                x: dim,
                y: data.z[countryIndex][dimIndex]
            }))
        }));

        const chartOptions = {
            ...this.defaultOptions,
            series: series,
            chart: {
                ...this.defaultOptions.chart,
                type: 'heatmap',
                height: height
            },
            colors: colors,
            xaxis: {
                categories: data.dims,
                labels: {
                    rotate: -45,
                    style: {
                        fontSize: '10px'
                    }
                }
            },
            yaxis: {
                labels: {
                    style: {
                        fontSize: '10px'
                    }
                }
            },
            plotOptions: {
                heatmap: {
                    shadeIntensity: 0.5,
                    colorScale: {
                        ranges: [
                            { from: 0, to: 1, color: colors[0] },
                            { from: 1, to: 5, color: colors[1] },
                            { from: 5, to: 15, color: colors[2] },
                            { from: 15, to: 30, color: colors[3] },
                            { from: 30, to: 100, color: colors[4] }
                        ]
                    }
                }
            },
            dataLabels: {
                enabled: true,
                style: {
                    colors: ['#fff']
                },
                formatter: function(val) {
                    return val > 0 ? val.toFixed(1) + '%' : '';
                }
            },
            tooltip: {
                y: {
                    formatter: function(val) {
                        return val.toFixed(1) + '%';
                    }
                }
            },
            title: title ? { text: title, align: 'center', style: { fontSize: '18px', fontWeight: 600, color: '#333' } } : undefined
        };

        try {
            const chart = new ApexCharts(element, chartOptions);
            chart.render();
            this.chartInstances[elementId] = chart;
            return chart;
        } catch (error) {
            console.error(`Error creating heatmap chart for ${elementId}:`, error);
            element.innerHTML = `<div style="text-align: center; padding: 20px;"><p style="color: #dc3545;">Heatmap Error</p><p style="font-size: 12px;">${error.message}</p></div>`;
            return null;
        }
    },

    /**
     * Creates a horizontal bar chart using ApexCharts
     *
     * @param {string} elementId - ID of the element to render chart in
     * @param {Array<string>} labels - Array of labels
     * @param {Array<number>} values - Array of values
     * @param {Object} options - Additional chart options
     */
    createBarChart(elementId, labels, values, options = {}) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.error(`Element with id ${elementId} not found`);
            return null;
        }
        element.innerHTML = ''; // Clear previous content

        const {
            title = '',
            height = 400,
            color = '#3886e1',
            formatValue = v => v.toString()
        } = options;

        const chartOptions = {
            ...this.defaultOptions,
            series: [{
                data: values
            }],
            chart: {
                ...this.defaultOptions.chart,
                type: 'bar',
                height: height
            },
            plotOptions: {
                bar: {
                    horizontal: true,
                    distributed: true,
                    dataLabels: {
                        position: 'top'
                    }
                }
            },
            colors: [color],
            xaxis: {
                categories: labels,
                labels: {
                    formatter: formatValue
                }
            },
            yaxis: {
                labels: {
                    style: {
                        fontSize: '10px'
                    }
                }
            },
            dataLabels: {
                enabled: true,
                textAnchor: 'start',
                style: {
                    colors: ['#fff']
                },
                formatter: formatValue,
                offsetX: 0
            },
            tooltip: {
                y: {
                    formatter: formatValue
                }
            },
            title: title ? { text: title, align: 'center', style: { fontSize: '18px', fontWeight: 600, color: '#333' } } : undefined,
            legend: {
                show: false
            }
        };

        try {
            const chart = new ApexCharts(element, chartOptions);
            chart.render();
            this.chartInstances[elementId] = chart;
            return chart;
        } catch (error) {
            console.error(`Error creating bar chart for ${elementId}:`, error);
            element.innerHTML = `<div style="text-align: center; padding: 20px;"><p style="color: #dc3545;">Bar Chart Error</p><p style="font-size: 12px;">${error.message}</p></div>`;
            return null;
        }
    },

    /**
     * Generates an array of default colors.
     * @param {number} count - The number of colors to generate.
     * @returns {Array<string>}
     */
    generateColors(count) {
        const colors = [
            '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
            '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9',
            '#F8C471', '#82E0AA', '#F1948A', '#85C1E9', '#F4D03F'
        ];
        const result = [];
        for (let i = 0; i < count; i++) {
            result.push(colors[i % colors.length]);
        }
        return result;
    },

    /**
     * Retrieves the default color palette.
     * @param {number} [count] - The number of colors to return.
     */
    getColorPalette(count) {
        // Implementation of getColorPalette method
    }
}; 