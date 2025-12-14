# analysis_toolkit.py
import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QWidget,
							 QStackedWidget, QListWidget, QAbstractItemView, QSpinBox, QLabel,
							 QTextEdit, QFileDialog, QMessageBox,
							 QProgressDialog, QApplication, QCheckBox)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

# Define which analyses are text-only - so that plots are removed
TEXT_ONLY_ANALYSES = ["Top Correlation Pairs", "Export Summary Statistics"]
FORCED_CATEGORICAL_COLS = ["age"]

def format_col_name(name, _):
	"""Simple placeholder for formatting column names for display."""
	return name.replace('_', ' ').title()


def engineer_features(df):
	"""Creates new, insightful columns from existing data."""
	print("\n--- Engineering Features ---")

	# Create a dictionary to hold all new columns. We'll add them all at once.
	new_features = {}

	estate_types = ['nobles', 'clergy', 'burghers', 'peasants', 'dhimmi', 'tribes', 'cossacks']

	# Safely get columns that exist in the dataframe
	pop_cols = [f'{e}_population' for e in estate_types if f'{e}_population' in df.columns]
	power_cols = [f'{e}_relative_power' for e in estate_types if f'{e}_relative_power' in df.columns]
	sat_cols = [f'{e}_satisfaction' for e in estate_types if f'{e}_satisfaction' in df.columns]

	# Aggregate
	new_features['total_population'] = df[pop_cols].sum(axis=1)
	new_features['total_estate_power'] = df[power_cols].sum(axis=1)
	new_features['avg_estate_satisfaction'] = df[sat_cols].mean(axis=1)

	# Mix
	new_features['debt_to_income_ratio'] = np.where(df['income'] > 0, df['total_debt'] / (df['income'] * 12), 0)
	new_features['army_to_population_ratio'] = np.where(new_features['total_population'] > 0,
														df['army_size'] / new_features['total_population'], 0)

	# Estate Relative Income Percentage
	for estate in estate_types:
		# Define the source column (the estate's own income) and the new column name
		source_col = f'{estate}_income_before_tax'
		new_col = f'{estate}_income_vs_government_%'

		if source_col in df.columns:
			new_features[new_col] = np.where(
				df['income'] > 0,
				(df[source_col] / df['income']) * 100,
				0
			)
		else:
			print(f"  - Warning: Source column '{source_col}' not found. Skipping '{new_col}'.")

	# Add Decade and Age columns ---
	if 'year' in df.columns:
		# Floor division to get the start of the decade (e.g., 1753 -> 1750)
		new_features['decade'] = (df['year'] // 10) * 10
		# Calculate the century number (e.g., 1753 -> 18th century)
		new_features['century'] = (df['year'] // 100) + 1
		new_features['age'] = ((df['year'] - 37) // 100) - 12
		print("  - Added 'decade' and 'century' columns.")
	else:
		print("  - Warning: 'year' column not found. Skipping decade and century features.")
	# --- END of new logic ---

	print("Feature engineering complete.")

	df = pd.concat([df, pd.DataFrame(new_features)], axis=1)
	return df


def get_top_correlations(df, original_columns, n=50):
	"""
	Calculates the correlation matrix and returns a formatted string 
	of the top N strongest correlations.
	"""
	print(f"\n--- Finding the Top {n} Strongest Correlations ---")
	numeric_df = df.select_dtypes(include=np.number)
	corr_matrix = numeric_df.corr()
	corr_stacked = corr_matrix.stack()
	corr_pairs = corr_stacked.reset_index()
	corr_pairs.columns = ['Variable 1', 'Variable 2', 'Correlation']
	corr_pairs['Abs Correlation'] = corr_pairs['Correlation'].abs()
	corr_pairs = corr_pairs[corr_pairs['Variable 1'] != corr_pairs['Variable 2']]
	corr_pairs['sorted_vars'] = corr_pairs.apply(lambda row: tuple(sorted((row['Variable 1'], row['Variable 2']))),
												 axis=1)
	corr_pairs = corr_pairs.drop_duplicates(subset=['sorted_vars'])
	corr_pairs = corr_pairs.drop(columns=['sorted_vars'])
	top_correlations = corr_pairs.sort_values(by='Abs Correlation', ascending=False).head(n)
	top_correlations = top_correlations.reset_index(drop=True)

	# --- Build a formatted string for the GUI output ---
	output_lines = []
	output_lines.append(f"--- Top {n} Strongest Correlation Pairs (Positive & Negative) ---")
	header = f"{'Rank':<5} {'Variable 1':<40} {'Variable 2':<40} {'Correlation':<15}"
	output_lines.append(header)
	output_lines.append("-" * (len(header) + 5))
	for index, row in top_correlations.iterrows():
		rank = index + 1
		var1 = format_col_name(row['Variable 1'], original_columns)
		var2 = format_col_name(row['Variable 2'], original_columns)
		corr_value = row['Correlation']
		output_lines.append(f"{rank:<5} {var1:<40} {var2:<40} {corr_value:<15.4f}")

	return "\n".join(output_lines)


class AnalysisToolkitDialog(QDialog):
	"""A dialog window for performing advanced data analysis on country data."""

	def __init__(self, country_df, parent=None):
		super().__init__(parent)
		self.setWindowTitle("Data Analysis Toolkit")
		self.setGeometry(150, 150, 1600, 800)

		# The dialog now receives a DataFrame directly
		if country_df is None or country_df.empty:
			self.df = pd.DataFrame()
			self.original_columns = []
		else:
			# Store original columns before adding new ones
			self.original_columns = country_df.columns.tolist()
			self.df = engineer_features(country_df)

		# Main layout
		self.main_layout = QHBoxLayout(self)

		# Left panel for controls
		self.controls_panel = QWidget()
		self.controls_layout = QVBoxLayout(self.controls_panel)
		self.main_layout.addWidget(self.controls_panel, 1)  # Takes 1/3 of space

		# Right panel for results
		self.results_panel = QWidget()
		self.results_layout = QVBoxLayout(self.results_panel)
		self.main_layout.addWidget(self.results_panel, 1)  # Takes 2/3 of space

		self._create_controls_panel()
		self._create_results_panel()

	def _create_controls_panel(self):
		# Analysis type selector
		self.analysis_selector = QComboBox()
		self.analysis_selector.addItems([
			"Select Analysis...",
			"Exploratory Data Analysis (EDA)",
			"Correlation Matrix",
			"Top Correlation Pairs",
			"Country Clustering (K-Means)",
			"Export Summary Statistics"
		])
		self.controls_layout.addWidget(self.analysis_selector)

		# Stacked widget for context-specific controls
		self.controls_stack = QStackedWidget()
		self.controls_layout.addWidget(self.controls_stack)

		# Add empty widget for the "Select..." state
		self.controls_stack.addWidget(QWidget())
		# Add control widgets for each analysis type
		# self.controls_stack.addWidget(QWidget()) # Empty widget
		self.controls_stack.addWidget(self._create_eda_controls())
		self.controls_stack.addWidget(self._create_correlation_controls())
		self.controls_stack.addWidget(self._create_top_corr_controls())
		self.controls_stack.addWidget(self._create_clustering_controls())
		self.controls_stack.addWidget(self._create_summary_export_controls())

		self.analysis_selector.currentIndexChanged.connect(self._on_analysis_changed)

		# Run button
		self.run_button = QPushButton("Run Analysis")
		self.run_button.clicked.connect(self.run_analysis)
		self.controls_layout.addWidget(self.run_button)
		self.controls_layout.addStretch()

	def _create_top_corr_controls(self):
		"""Creates the controls for the Top Correlations analysis."""
		widget = QWidget()
		layout = QVBoxLayout(widget)

		layout.addWidget(QLabel("Find Strongest Relationships:"))
		layout.addWidget(QLabel("Number of top pairs to find:"))

		self.top_corr_n_selector = QSpinBox()
		self.top_corr_n_selector.setRange(10, 500)
		self.top_corr_n_selector.setValue(50)
		self.top_corr_n_selector.setSingleStep(10)
		layout.addWidget(self.top_corr_n_selector)

		layout.addStretch()
		return widget

	def _get_categorical_columns(self):
		"""Returns a list of non-numeric columns suitable for grouping."""
		if self.df.empty:
			return []

		suitable_cols = self.df.select_dtypes(include=['object', 'category']).columns.tolist()

		for col in FORCED_CATEGORICAL_COLS:
			if col not in suitable_cols:
				suitable_cols.append(col)

		return suitable_cols

	def _on_analysis_changed(self, index):
		"""Handles state changes, including widget visibility, when a new analysis is selected."""
		self.controls_stack.setCurrentIndex(index)

		analysis_type = self.analysis_selector.currentText()

		# Show or hide the plot canvas based on the analysis type
		if analysis_type in TEXT_ONLY_ANALYSES:
			self.canvas.setVisible(False)
		else:
			self.canvas.setVisible(True)

	def _get_numeric_columns(self):
		if self.df.empty:
			return []
		return self.df.select_dtypes(include=['number']).columns.tolist()

	def _create_summary_export_controls(self):
		"""Creates controls for both ungrouped (CSV) and grouped (Excel) summary exports."""
		widget = QWidget()
		layout = QVBoxLayout(widget)

		# --- Section 1: Ungrouped Export ---
		layout.addWidget(QLabel("Ungrouped Export (to CSV):"))
		layout.addWidget(QLabel("Calculates a single summary for all numeric variables."))
		
		ungrouped_button = QPushButton("Export Ungrouped Summary (CSV)")
		ungrouped_button.clicked.connect(self._export_ungrouped_summary)
		layout.addWidget(ungrouped_button)

		# Add a separator
		separator = QWidget()
		separator.setFixedHeight(20)
		layout.addWidget(separator)

		# --- Section 2: Grouped Export ---
		layout.addWidget(QLabel("Grouped Export (to Excel Sheets):"))
		layout.addWidget(QLabel("Group stats by a category and export each to a separate Excel sheet."))

		layout.addWidget(QLabel("Group by:"))
		self.summary_group_by_selector = QComboBox()
		self.summary_group_by_selector.addItems(self._get_categorical_columns())
		layout.addWidget(self.summary_group_by_selector)

		# Add the normalization checkbox
		self.summary_normalize_checkbox = QCheckBox("Normalize by num_locations")
		self.summary_normalize_checkbox.setToolTip(
			"If checked, divides extensive variables (income, population, etc.)\n"
			"by 'num_locations' before calculating statistics."
		)
		layout.addWidget(self.summary_normalize_checkbox)
		# --- END of new UI element ---

		grouped_button = QPushButton("Export Grouped Summary (Excel)")
		grouped_button.clicked.connect(self._export_grouped_summary)
		layout.addWidget(grouped_button)

		layout.addStretch()
		return widget

	def _create_eda_controls(self):
		widget = QWidget()
		layout = QVBoxLayout(widget)

		# Country selector
		layout.addWidget(QLabel("Select Country:"))
		self.eda_country_selector = QComboBox()
		if not self.df.empty:
			countries = sorted(self.df['name'].unique())
			self.eda_country_selector.addItems(countries)
		layout.addWidget(self.eda_country_selector)

		# Variable selector
		layout.addWidget(QLabel("Select Variable:"))
		self.eda_variable_selector = QComboBox()
		self.eda_variable_selector.addItems(self._get_numeric_columns())
		layout.addWidget(self.eda_variable_selector)

		layout.addStretch()
		return widget

	def _create_correlation_controls(self):
		widget = QWidget()
		layout = QVBoxLayout(widget)

		layout.addWidget(QLabel("Direct Export:"))
		self.corr_export_full_button = QPushButton("Export Full Matrix to CSV")
		self.corr_export_full_button.setToolTip(
			"Calculates and exports the correlation matrix for ALL numeric columns.")
		self.corr_export_full_button.setEnabled(True)  # Always enabled
		self.corr_export_full_button.clicked.connect(self.export_correlation_csv)
		layout.addWidget(self.corr_export_full_button)

		layout.addWidget(QWidget())  # Spacer

		# --- UI for generating a selective heatmap ---
		layout.addWidget(QLabel("Heatmap Generation (for visualization):"))
		layout.addWidget(QLabel("Select 2 or more variables to generate a heatmap:"))

		self.corr_variable_list = QListWidget()
		self.corr_variable_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
		self.corr_variable_list.addItems(self._get_numeric_columns())
		layout.addWidget(self.corr_variable_list)

		self.corr_export_button = QPushButton("Export Matrix to CSV")
		self.corr_export_button.setEnabled(True)
		self.corr_export_button.clicked.connect(self.export_correlation_csv)
		layout.addWidget(self.corr_export_button)

		return widget

	def _create_clustering_controls(self):
		widget = QWidget()
		layout = QVBoxLayout(widget)
		layout.addWidget(QLabel("Select variables for clustering:"))

		self.cluster_variable_list = QListWidget()
		self.cluster_variable_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
		self.cluster_variable_list.addItems(self._get_numeric_columns())
		layout.addWidget(self.cluster_variable_list)

		layout.addWidget(QLabel("Number of Clusters (K):"))
		self.cluster_k_selector = QSpinBox()
		self.cluster_k_selector.setRange(2, 20)
		self.cluster_k_selector.setValue(5)
		layout.addWidget(self.cluster_k_selector)

		return widget

	def _create_results_panel(self):
		# Matplotlib canvas for plots
		self.fig, self.ax = plt.subplots()
		self.canvas = FigureCanvas(self.fig)
		self.results_layout.addWidget(self.canvas, 2)  # Plot takes more space

		# Text/Table output area
		self.output_area = QTextEdit()
		self.output_area.setReadOnly(True)
		self.results_layout.addWidget(self.output_area, 1)

	def run_analysis(self):
		if self.df.empty:
			self.output_area.setText("No data loaded. Please load logs in the main window first.")
			return

		analysis_type = self.analysis_selector.currentText()
		self.ax.clear()
		self.output_area.clear()

		if analysis_type == "Exploratory Data Analysis (EDA)":
			self._perform_eda()
		elif analysis_type == "Correlation Matrix":
			self._perform_correlation()
		elif analysis_type == "Top Correlation Pairs":
			self._perform_top_correlations()
		elif analysis_type == "Country Clustering (K-Means)":
			self._perform_clustering()
		elif analysis_type == "Export Summary Statistics":
			# For this mode, the "Run" button will just generate a preview.
			self._perform_summary_preview()

		self.canvas.draw()

	def _perform_eda(self):
		country = self.eda_country_selector.currentText()
		variable = self.eda_variable_selector.currentText()

		country_df = self.df[self.df['name'] == country]

		# Display summary statistics
		stats = country_df[variable].describe()
		self.output_area.setText(f"--- Summary Statistics for '{variable}' in {country} ---\n\n{stats.to_string()}")

		# Plot
		self.ax.set_title(f"EDA for '{variable}' in {country}")
		sns.histplot(country_df[variable], kde=True, ax=self.ax, label="Distribution")
		self.ax.set_xlabel(variable)

		ax2 = self.ax.twinx()
		sns.lineplot(x='year', y=variable, data=country_df, ax=ax2, color='red', marker='o', label="Trend over Time")
		ax2.set_ylabel(f"{variable} (Time Trend)")
		self.fig.legend()

	def _perform_summary_preview(self):
		"""Calculates and displays a preview of the transposed summary statistics."""
		if self.df.empty:
			return

		numeric_df = self.df.select_dtypes(include=np.number)
		summary_df = numeric_df.describe()
		transposed_summary = summary_df.transpose()

		font = self.output_area.font()
		font.setFamily("Courier New")
		self.output_area.setFont(font)

		self.output_area.setText("--- Transposed Summary Statistics Preview ---\n\n" + transposed_summary.to_string())


	def _export_ungrouped_summary(self):
		"""Calculates and exports a single, ungrouped summary to a CSV file."""
		if self.df.empty:
			QMessageBox.warning(self, "Export Error", "No data is loaded.")
			return
	
		print("Calculating ungrouped summary statistics for export...")
		numeric_df = self.df.select_dtypes(include=np.number)
		transposed_summary = numeric_df.describe().transpose()
	
		file_path, _ = QFileDialog.getSaveFileName(
			self, "Save Ungrouped Summary", "ungrouped_summary_stats.csv", "CSV Files (*.csv)"
		)
	
		if file_path:
			try:
				transposed_summary.to_csv(file_path)
				QMessageBox.information(self, "Export Successful", f"Ungrouped summary saved to:\n{file_path}")
				self._perform_summary_preview()
			except Exception as e:
				QMessageBox.critical(self, "Export Failed", f"An error occurred while saving the file:\n{e}")
	
	
	def _sanitize_sheet_name(self, name):
		"""Sanitizes a string to be a valid Excel sheet name."""
		# Convert to string, remove invalid characters, and truncate to 31 chars
		name_str = str(name)
		invalid_chars = r'[\\/*?:\[\]]'
		sanitized = re.sub(invalid_chars, "_", name_str)
		return sanitized[:31]


	def _export_grouped_summary(self):
		"""Groups data by a category and exports each group's summary to an Excel sheet."""
		if self.df.empty:
			QMessageBox.warning(self, "Export Error", "No data is loaded.")
			return
	
		group_by_col = self.summary_group_by_selector.currentText()
		if not group_by_col:
			QMessageBox.warning(self, "Selection Error", "Please select a category to group by.")
			return
	
		# --- Check the state of the new checkbox ---
		is_normalized = self.summary_normalize_checkbox.isChecked()

		# Set a dynamic filename and title for the dialog
		default_filename = f"summary_stats_by_{group_by_col}_normalized.xlsx" if is_normalized else f"summary_stats_by_{group_by_col}.xlsx"
		dialog_title = "Save Normalized Grouped Summary" if is_normalized else "Save Grouped Summary"

		file_path, _ = QFileDialog.getSaveFileName(
			self, dialog_title, default_filename, "Excel Files (*.xlsx)"
		)
	
		if not file_path:
			return
	
		sheets_written = 0
		try:
			# Use ExcelWriter to write to multiple sheets
			with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
				# Explicitly drop NaN values before getting unique groups ---
				groups = self.df[group_by_col].dropna().unique()

				if not groups.any():
					QMessageBox.warning(self, "No Data", f"The selected column '{group_by_col}' contains no valid data to group by.")
					return
	
				for group in groups:
					print(f"  - Processing group: {group}")
					# Filter the dataframe for the current group
					subset_df = self.df[self.df[group_by_col] == group].copy()
	
					# Safeguard: Skip if the subset is somehow empty
					if subset_df.empty:
						continue

					# Perform normalization if the checkbox is ticked
					if is_normalized:
						if 'num_locations' not in subset_df.columns or subset_df['num_locations'].sum() == 0:
							print(f"	- Skipping normalization for group '{group}' due to missing or zero 'num_locations'.")
						else:
							# Define extensive columns to be normalized
							extensive_cols = [
								'income', 'total_debt', 'army_size', 'max_manpower', 'max_sailors',
								'military_strength', 'navy_size', 'navy_strength', 'economical_base',
								'estimated_monthly_income', 'total_coastal_population'
							]
							estate_types = ['nobles', 'clergy', 'burghers', 'peasants', 'dhimmi', 'tribes', 'cossacks']
							for estate in estate_types:
								extensive_cols.extend([
									f'{estate}_gold', f'{estate}_balance', f'{estate}_food_income',
									f'{estate}_trade_income', f'{estate}_income_before_tax', f'{estate}_tax',
									f'{estate}_expense', f'{estate}_taxable_income', f'{estate}_population'
								])

							for col in extensive_cols:
								if col in subset_df.columns:
									# Use np.where for safe division
									subset_df[col] = np.where(
										subset_df['num_locations'] > 0,
										subset_df[col] / subset_df['num_locations'],
										0
									)

					numeric_subset = subset_df.select_dtypes(include=np.number)

					# Safeguard: Skip if there are no numeric columns in the subset
					if numeric_subset.empty:
						continue

					summary = numeric_subset.describe().transpose()
					# Sanitize the group name to be a valid sheet name
					sheet_name = self._sanitize_sheet_name(group)
					# Write the summary to a new sheet
					summary.to_excel(writer, sheet_name=sheet_name)
					sheets_written += 1

			# Check if any sheets were actually written
			if sheets_written > 0:
				QMessageBox.information(self, "Export Successful",
										f"Grouped summary with {sheets_written} sheets saved to:\n{file_path}")
			else:
				QMessageBox.warning(self, "Export Warning",
									"No valid data groups were found to export. The Excel file was not created.")
	
		except ImportError:
			QMessageBox.critical(self, "Dependency Missing",
								 "The 'openpyxl' library is required for Excel export.\n\n"
								 "Please install it by running:\npip install openpyxl")
		except Exception as e:
			QMessageBox.critical(self, "Export Failed", f"An error occurred while saving the file:\n{e}")
	

	def _export_summary_statistics(self):
		"""Calculates and exports the transposed summary statistics to a CSV file."""
		if self.df.empty:
			QMessageBox.warning(self, "Export Error", "No data is loaded.")
			return

		print("Calculating summary statistics for export...")
		numeric_df = self.df.select_dtypes(include=np.number)
		summary_df = numeric_df.describe()
		transposed_summary = summary_df.transpose()

		file_path, _ = QFileDialog.getSaveFileName(
			self,
			"Save Transposed Summary Statistics",
			"transposed_summary_stats.csv",
			"CSV Files (*.csv);;All Files (*)"
		)

		if file_path:
			try:
				transposed_summary.to_csv(file_path)
				QMessageBox.information(self, "Export Successful",
										f"Transposed summary statistics successfully saved to:\n{file_path}")
				# Also show the preview after a successful export
				self._perform_summary_preview()
			except Exception as e:
				QMessageBox.critical(self, "Export Failed", f"An error occurred while saving the file:\n{e}")

	def _perform_correlation(self):
		selected_items = self.corr_variable_list.selectedItems()
		variables = [item.text() for item in selected_items]

		if len(variables) < 2:
			self.output_area.setText(
				"Please select at least two variables from the list and click 'Run Analysis' to generate a heatmap.")
			return

		corr_df = self.df[variables]
		matrix = corr_df.corr()

		self.output_area.setText(f"--- Correlation Matrix ---\n\n{matrix.to_string()}")

		sns.heatmap(matrix, annot=True, cmap='coolwarm', fmt=".2f", ax=self.ax)
		self.ax.set_title("Correlation Heatmap")
		plt.setp(self.ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")
		plt.setp(self.ax.get_yticklabels(), rotation=0)
		self.fig.tight_layout()

	def _perform_clustering(self):
		selected_items = self.cluster_variable_list.selectedItems()
		variables = [item.text() for item in selected_items]
		k = self.cluster_k_selector.value()

		if len(variables) < 2:
			self.output_area.setText("Please select at least two variables for clustering.")
			return

		# Use data from the latest year for clustering
		latest_year = self.df['year'].max()
		cluster_df = self.df[self.df['year'] == latest_year][variables].dropna()

		if len(cluster_df) < k:
			self.output_area.setText("Not enough data for the selected number of clusters.")
			return

		# Scale data
		scaler = StandardScaler()
		scaled_data = scaler.fit_transform(cluster_df)

		# K-Means
		kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
		cluster_df['cluster'] = kmeans.fit_predict(scaled_data)

		# PCA for visualization
		pca = PCA(n_components=2)
		pca_result = pca.fit_transform(scaled_data)
		cluster_df['pca1'] = pca_result[:, 0]
		cluster_df['pca2'] = pca_result[:, 1]

		# Output results
		cluster_summary = cluster_df['cluster'].value_counts().sort_index()
		self.output_area.setText(f"--- Clustering Results (Latest Year: {latest_year}) ---\n\n"
								 f"Countries per cluster:\n{cluster_summary.to_string()}")

		# Plot
		sns.scatterplot(x='pca1', y='pca2', hue='cluster', data=cluster_df, palette='viridis', ax=self.ax, s=100,
						alpha=0.8)
		self.ax.set_title(f"Country Clusters (K={k}) based on selected variables (visualized with PCA)")
		self.ax.set_xlabel("Principal Component 1")
		self.ax.set_ylabel("Principal Component 2")
		self.ax.legend(title="Cluster")

	def export_correlation_csv(self):
		"""Calculates the correlation matrix for all numeric columns and exports it."""
		if self.df.empty:
			QMessageBox.warning(self, "Export Error", "No data is loaded.")
			return

		# --- Setup and show the indeterminate progress dialog ---
		progress_dialog = QProgressDialog("Calculating full correlation matrix...", "Cancel", 0, 0, self)
		progress_dialog.setWindowTitle("Processing Data")
		progress_dialog.setModal(True)
		# Setting the range to (0, 0) enables the indeterminate "busy" animation.
		progress_dialog.setRange(0, 0)
		progress_dialog.show()
		# This is crucial to ensure the dialog appears before the heavy calculation starts.
		QApplication.processEvents()

		try:
			print("Calculating full correlation matrix for export...")

			# Select only numeric columns for correlation
			numeric_df = self.df.select_dtypes(include=['number'])
			matrix = numeric_df.corr()

			# Close the progress dialog as soon as the calculation is done
			progress_dialog.close()

			# Ask the user where to save the result
			file_path, _ = QFileDialog.getSaveFileName(
				self,
				"Save Correlation Matrix",
				"correlation_matrix.csv",
				"CSV Files (*.csv);;All Files (*)"
			)

			if file_path:
				try:
					matrix.to_csv(file_path)
					QMessageBox.information(self, "Export Successful",
											f"Full correlation matrix successfully saved to:\n{file_path}")
				except Exception as e:
					QMessageBox.critical(self, "Export Failed", f"An error occurred while saving the file:\n{e}")

		except Exception as e:
			# Catch any errors during the correlation calculation itself
			QMessageBox.critical(self, "Calculation Failed",
								 f"An error occurred during the correlation calculation:\n{e}")

		finally:
			# This ensures the progress dialog is always closed, even if an error occurs.
			progress_dialog.close()

	def _perform_top_correlations(self):
		"""Performs the top correlations analysis and displays the results."""
		n = self.top_corr_n_selector.value()

		# Use a monospace font for the text area to ensure alignment
		font = self.output_area.font()
		font.setFamily("Courier New")
		self.output_area.setFont(font)

		# Call the analysis function and set the output
		correlation_report = get_top_correlations(self.df, self.original_columns, n)
		self.output_area.setText(correlation_report)
