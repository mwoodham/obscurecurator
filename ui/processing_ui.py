from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLabel, QProgressBar, QGroupBox, QListWidget, QListWidgetItem,
    QDialog, QDialogButtonBox, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QCheckBox, QComboBox
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QSize
from PySide6.QtGui import QColor, QIcon, QFont

from database.schema import MediaFile, VideoSegment, ProcessingStatus
import logging
import time
from datetime import datetime

logger = logging.getLogger("processing_ui")

class ProcessingStatusUI(QWidget):
    """Enhanced UI for monitoring and controlling the processing pipeline."""
    
    def __init__(self, processor_manager, db_manager):
        super().__init__()
        self.processor_manager = processor_manager
        self.db_manager = db_manager
        self.setup_ui()
        
        # Start update timer
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_status)
        self.update_timer.start(1000)  # Update every second
    
    def setup_ui(self):
        """Setup the UI components."""
        main_layout = QVBoxLayout(self)
        
        # Status overview
        status_group = QGroupBox("Processing Status")
        status_layout = QVBoxLayout(status_group)
        
        # Status indicators
        status_grid = QHBoxLayout()
        
        # Queue status
        queue_layout = QVBoxLayout()
        self.queue_label = QLabel("Queue: 0 files")
        queue_layout.addWidget(self.queue_label)
        status_grid.addLayout(queue_layout)
        
        # Processing status
        processing_layout = QVBoxLayout()
        self.processing_status = QLabel("Status: Idle")
        self.processing_status.setStyleSheet("font-weight: bold;")
        processing_layout.addWidget(self.processing_status)
        status_grid.addLayout(processing_layout)
        
        # Progress counters
        counters_layout = QVBoxLayout()
        self.progress_counter = QLabel("Processed: 0 / 0 files")
        counters_layout.addWidget(self.progress_counter)
        status_grid.addLayout(counters_layout)
        
        status_layout.addLayout(status_grid)
        
        # Overall progress
        overall_layout = QHBoxLayout()
        overall_layout.addWidget(QLabel("Overall Progress:"))
        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        overall_layout.addWidget(self.overall_progress)
        status_layout.addLayout(overall_layout)
        
        # Current file progress
        file_layout = QHBoxLayout()
        file_layout.addWidget(QLabel("Current File:"))
        self.current_file_label = QLabel("None")
        file_layout.addWidget(self.current_file_label)
        status_layout.addLayout(file_layout)
        
        # Current file progress bar
        self.file_progress = QProgressBar()
        self.file_progress.setRange(0, 100)
        self.file_progress.setValue(0)
        status_layout.addWidget(self.file_progress)
        
        main_layout.addWidget(status_group)
        
        # Control buttons
        controls_group = QGroupBox("Processing Controls")
        controls_layout = QHBoxLayout(controls_group)
        
        # Start/Restart button
        self.start_button = QPushButton("Start Processing")
        self.start_button.clicked.connect(self.start_processing)
        controls_layout.addWidget(self.start_button)
        
        # Pause/Resume button
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.pause_processing)
        self.pause_button.setEnabled(False)
        controls_layout.addWidget(self.pause_button)
        
        # Retry failed button
        self.retry_button = QPushButton("Retry Failed")
        self.retry_button.clicked.connect(self.retry_failed)
        controls_layout.addWidget(self.retry_button)
        
        # Show details button
        self.details_button = QPushButton("Show Details")
        self.details_button.clicked.connect(self.show_details)
        controls_layout.addWidget(self.details_button)
        
        main_layout.addWidget(controls_group)
        
        # Files list
        files_group = QGroupBox("Processing Queue")
        files_layout = QVBoxLayout(files_group)
        
        self.files_list = QListWidget()
        files_layout.addWidget(self.files_list)
        
        main_layout.addWidget(files_group)
    
    def update_status(self):
        """Update the status display with current information."""
        try:
            # Get processing status
            status = self.processor_manager.get_processing_status()
            
            # Update queue status
            self.queue_label.setText(f"Queue: {status['queue_length']} files")
            
            # Update processing status
            if status['is_processing']:
                self.processing_status.setText("Status: Processing")
                self.processing_status.setStyleSheet("font-weight: bold; color: green;")
                self.start_button.setText("Stop Processing")
                self.pause_button.setEnabled(True)
            else:
                self.processing_status.setText("Status: Idle")
                self.processing_status.setStyleSheet("font-weight: bold; color: black;")
                self.start_button.setText("Start Processing")
                self.pause_button.setEnabled(False)
            
            # Update progress counters
            self.progress_counter.setText(f"Processed: {status['processed_files']} / {status['total_files']} files")
            
            # Update progress bars
            self.overall_progress.setValue(int(status['overall_progress']))
            self.file_progress.setValue(int(status['current_file_progress']))
            
            # Get current files from DB
            self.update_files_list()
            
        except Exception as e:
            logger.error(f"Error updating status: {e}", exc_info=True)
    
    def update_files_list(self):
        """Update the list of files with their current status."""
        try:
            # Get current processing file if any
            session = self.db_manager.get_session()
            
            # Get in-progress files
            in_progress_files = session.query(MediaFile).filter_by(
                processing_status=ProcessingStatus.IN_PROGRESS
            ).all()
            
            if in_progress_files:
                self.current_file_label.setText(in_progress_files[0].filename)
            else:
                self.current_file_label.setText("None")
            
            # Update list if empty (only first time)
            if self.files_list.count() == 0:
                # Get all files ordered by status
                files = session.query(MediaFile).order_by(
                    MediaFile.processing_status
                ).limit(100).all()  # Limit to 100 files for performance
                
                # Clear list
                self.files_list.clear()
                
                # Add files to list
                for file in files:
                    item = QListWidgetItem(f"{file.filename} - {file.processing_status.value}")
                    
                    # Set color based on status
                    if file.processing_status == ProcessingStatus.COMPLETED:
                        item.setForeground(QColor("green"))
                    elif file.processing_status == ProcessingStatus.IN_PROGRESS:
                        item.setForeground(QColor("blue"))
                    elif file.processing_status == ProcessingStatus.FAILED:
                        item.setForeground(QColor("red"))
                    
                    self.files_list.addItem(item)
            
            session.close()
            
        except Exception as e:
            logger.error(f"Error updating files list: {e}", exc_info=True)
    
    def start_processing(self):
        """Start or stop processing based on current state."""
        try:
            status = self.processor_manager.get_processing_status()
            
            if status['is_processing']:
                # Stop processing
                self.processor_manager.stop_processing()
                self.start_button.setText("Start Processing")
                self.pause_button.setEnabled(False)
            else:
                # Start processing
                self.processor_manager.process_all()
                self.start_button.setText("Stop Processing")
                self.pause_button.setEnabled(True)
        except Exception as e:
            logger.error(f"Error controlling processing: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Error: {str(e)}")
    
    def pause_processing(self):
        """Pause or resume processing."""
        # To be implemented with a pause mechanism in the processor manager
        QMessageBox.information(self, "Not Implemented", "Pause functionality not implemented yet")
    
    def retry_failed(self):
        """Retry all failed files."""
        try:
            count = self.processor_manager.resume_failed()
            QMessageBox.information(self, "Retry Failed", f"Queued {count} failed files for reprocessing")
        except Exception as e:
            logger.error(f"Error retrying failed files: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Error: {str(e)}")
    
    def show_details(self):
        """Show detailed processing status dialog."""
        try:
            dialog = ProcessingDetailsDialog(self.db_manager, self)
            dialog.exec()
        except Exception as e:
            logger.error(f"Error showing details: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Error: {str(e)}")


class ProcessingDetailsDialog(QDialog):
    """Dialog showing detailed processing status and allowing fine-grained control."""
    
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setup_ui()
        self.load_data()
    
    def setup_ui(self):
        """Setup the dialog UI."""
        self.setWindowTitle("Processing Details")
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        
        # File status table
        file_group = QGroupBox("Files Status")
        file_layout = QVBoxLayout(file_group)
        
        self.files_table = QTableWidget()
        self.files_table.setColumnCount(7)
        self.files_table.setHorizontalHeaderLabels([
            "Filename", "Status", "Scene Detection", "Feature Extraction", 
            "Last Error", "Updated", "Actions"
        ])
        self.files_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.files_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.files_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        
        file_layout.addWidget(self.files_table)
        
        # Filters
        filter_layout = QHBoxLayout()
        
        self.show_completed = QCheckBox("Show Completed")
        self.show_completed.setChecked(True)
        self.show_completed.stateChanged.connect(self.load_data)
        filter_layout.addWidget(self.show_completed)
        
        self.show_failed = QCheckBox("Show Failed")
        self.show_failed.setChecked(True)
        self.show_failed.stateChanged.connect(self.load_data)
        filter_layout.addWidget(self.show_failed)
        
        self.show_pending = QCheckBox("Show Pending")
        self.show_pending.setChecked(True)
        self.show_pending.stateChanged.connect(self.load_data)
        filter_layout.addWidget(self.show_pending)
        
        filter_layout.addStretch()
        
        self.status_filter = QComboBox()
        self.status_filter.addItem("All Statuses")
        for status in ProcessingStatus:
            self.status_filter.addItem(status.value)
        self.status_filter.currentIndexChanged.connect(self.load_data)
        filter_layout.addWidget(self.status_filter)
        
        file_layout.addLayout(filter_layout)
        
        layout.addWidget(file_group)
        
        # Segment status
        segment_group = QGroupBox("Segments Status")
        segment_layout = QVBoxLayout(segment_group)
        
        self.segments_table = QTableWidget()
        self.segments_table.setColumnCount(6)
        self.segments_table.setHorizontalHeaderLabels([
            "File", "Start-End Frame", "Status", "Features", "Last Error", "Actions"
        ])
        self.segments_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.segments_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.segments_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        
        segment_layout.addWidget(self.segments_table)
        
        layout.addWidget(segment_group)
        
        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.accept)
        
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.load_data)
        button_box.addButton(refresh_button, QDialogButtonBox.ActionRole)
        
        layout.addWidget(button_box)
    
    def load_data(self):
        """Load data into tables."""
        session = self.db_manager.get_session()
        try:
            # Build query based on filters
            query = session.query(MediaFile)
            
            if not self.show_completed.isChecked():
                query = query.filter(MediaFile.processing_status != ProcessingStatus.COMPLETED)
            
            if not self.show_failed.isChecked():
                query = query.filter(MediaFile.processing_status != ProcessingStatus.FAILED)
            
            if not self.show_pending.isChecked():
                query = query.filter(MediaFile.processing_status != ProcessingStatus.PENDING)
            
            status_text = self.status_filter.currentText()
            if status_text != "All Statuses":
                query = query.filter(MediaFile.processing_status == ProcessingStatus(status_text))
            
            # Get files
            files = query.order_by(MediaFile.updated_at.desc()).limit(100).all()
            
            # Set table size
            self.files_table.setRowCount(len(files))
            
            # Fill table
            for i, file in enumerate(files):
                # Filename
                self.files_table.setItem(i, 0, QTableWidgetItem(file.filename))
                
                # Status
                status_item = QTableWidgetItem(file.processing_status.value)
                if file.processing_status == ProcessingStatus.COMPLETED:
                    status_item.setForeground(QColor("green"))
                elif file.processing_status == ProcessingStatus.IN_PROGRESS:
                    status_item.setForeground(QColor("blue"))
                elif file.processing_status == ProcessingStatus.FAILED:
                    status_item.setForeground(QColor("red"))
                self.files_table.setItem(i, 1, status_item)
                
                # Scene detection
                self.files_table.setItem(i, 2, QTableWidgetItem(
                    f"{file.scene_detection_progress:.1f}%" if file.scene_detection_progress else "Not started"
                ))
                
                # Feature extraction
                self.files_table.setItem(i, 3, QTableWidgetItem(
                    f"{file.feature_extraction_progress:.1f}%" if file.feature_extraction_progress else "Not started"
                ))
                
                # Last error
                self.files_table.setItem(i, 4, QTableWidgetItem(
                    file.last_error if file.last_error else ""
                ))
                
                # Updated
                updated = file.updated_at.strftime("%Y-%m-%d %H:%M:%S") if file.updated_at else ""
                self.files_table.setItem(i, 5, QTableWidgetItem(updated))
                
                # Actions button
                retry_button = QPushButton("Retry")
                retry_button.clicked.connect(lambda checked, file_id=file.id: self.retry_file(file_id))
                self.files_table.setCellWidget(i, 6, retry_button)
            
            # Get segments for the first file if any
            segments = []
            if files:
                segments = session.query(VideoSegment).filter_by(
                    source_file_id=files[0].id
                ).order_by(VideoSegment.start_frame).all()
            
            # Set segments table size
            self.segments_table.setRowCount(len(segments))
            
            # Fill segments table
            for i, segment in enumerate(segments):
                # File
                self.segments_table.setItem(i, 0, QTableWidgetItem(segment.source_file.filename))
                
                # Start-End Frame
                self.segments_table.setItem(i, 1, QTableWidgetItem(
                    f"{segment.start_frame}-{segment.end_frame} ({segment.duration:.2f}s)"
                ))
                
                # Status
                status_item = QTableWidgetItem(segment.processing_status.value)
                if segment.processing_status == ProcessingStatus.COMPLETED:
                    status_item.setForeground(QColor("green"))
                elif segment.processing_status == ProcessingStatus.IN_PROGRESS:
                    status_item.setForeground(QColor("blue"))
                elif segment.processing_status == ProcessingStatus.FAILED:
                    status_item.setForeground(QColor("red"))
                self.segments_table.setItem(i, 2, status_item)
                
                # Features
                self.segments_table.setItem(i, 3, QTableWidgetItem(
                    "Extracted" if segment.features_extracted else "Not extracted"
                ))
                
                # Last error
                self.segments_table.setItem(i, 4, QTableWidgetItem(
                    segment.last_error if segment.last_error else ""
                ))
                
                # Actions button
                retry_button = QPushButton("Retry")
                retry_button.clicked.connect(lambda checked, segment_id=segment.id: self.retry_segment(segment_id))
                self.segments_table.setCellWidget(i, 5, retry_button)
            
        except Exception as e:
            logger.error(f"Error loading data: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Error loading data: {str(e)}")
        finally:
            session.close()
    
    def retry_file(self, file_id):
        """Retry processing a failed file."""
        try:
            session = self.db_manager.get_session()
            file = session.query(MediaFile).get(file_id)
            
            if file:
                file.processing_status = ProcessingStatus.PENDING
                file.last_error = None
                session.commit()
                QMessageBox.information(self, "Retry File", f"File {file.filename} queued for reprocessing")
                self.load_data()
            
            session.close()
        except Exception as e:
            logger.error(f"Error retrying file: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Error: {str(e)}")
    
    def retry_segment(self, segment_id):
        """Retry processing a failed segment."""
        try:
            session = self.db_manager.get_session()
            segment = session.query(VideoSegment).get(segment_id)
            
            if segment:
                segment.processing_status = ProcessingStatus.PENDING
                segment.last_error = None
                session.commit()
                QMessageBox.information(self, "Retry Segment", f"Segment {segment.id} queued for reprocessing")
                self.load_data()
            
            session.close()
        except Exception as e:
            logger.error(f"Error retrying segment: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Error: {str(e)}")