import torch
from transformers import CLIPProcessor, CLIPModel
import cv2
import numpy as np
import io
import pickle
from PIL import Image
import time
from pathlib import Path
import config

class FeatureExtractor:
    def __init__(self, use_gpu=True):
        self.use_gpu = use_gpu and torch.cuda.is_available()
        self.device = torch.device('cuda' if self.use_gpu else 'cpu')
        
        # Initialize models
        self.clip_model = None
        self.clip_processor = None
        self.model_loaded = False
        
        print(f"Feature extractor initialized. GPU enabled: {self.use_gpu}")
    
    def load_models(self):
        """Load the CLIP model and processor."""
        if self.model_loaded:
            return
            
        print("Loading CLIP model...")
        start_time = time.time()
        
        # Load CLIP model
        self.clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(self.device)
        self.clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        
        self.model_loaded = True
        load_time = time.time() - start_time
        print(f"Models loaded on {self.device} in {load_time:.2f} seconds")
    
    def extract_frame_features(self, frame):
        """Extract CLIP features from a single frame.
        
        Args:
            frame: OpenCV BGR frame
            
        Returns:
            dict: Dictionary with feature vectors
        """
        if not self.model_loaded:
            self.load_models()
        
        # Convert BGR to RGB for PIL
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb_frame)
        
        # Process image for CLIP
        inputs = self.clip_processor(
            images=pil_image,
            return_tensors="pt"
        ).to(self.device)
        
        # Extract features
        with torch.no_grad():
            image_features = self.clip_model.get_image_features(**inputs)
            
        # Convert to numpy and normalize
        image_features = image_features.cpu().numpy().flatten()
        image_features = image_features / np.linalg.norm(image_features)
        
        # Create a histogram of colors (more basic visual feature)
        hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h_hist = cv2.calcHist([hsv_frame], [0], None, [20], [0, 180])
        s_hist = cv2.calcHist([hsv_frame], [1], None, [20], [0, 256])
        v_hist = cv2.calcHist([hsv_frame], [2], None, [20], [0, 256])
        
        # Normalize histograms
        h_hist = cv2.normalize(h_hist, h_hist, 0, 1, cv2.NORM_MINMAX)
        s_hist = cv2.normalize(s_hist, s_hist, 0, 1, cv2.NORM_MINMAX)
        v_hist = cv2.normalize(v_hist, v_hist, 0, 1, cv2.NORM_MINMAX)
        
        # Combine histograms
        color_hist = np.concatenate([h_hist, s_hist, v_hist]).flatten()
        
        # Calculate dominant colors
        pixels = hsv_frame.reshape(-1, 3)
        # Use k-means to find dominant colors (3 clusters)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, labels, centers = cv2.kmeans(
            np.float32(pixels[:10000]),  # Sample for speed
            3,  # 3 dominant colors
            None,
            criteria,
            10,
            cv2.KMEANS_RANDOM_CENTERS
        )
        # Convert back to BGR for visualization
        centers = centers.astype(np.uint8)
        dominant_colors = cv2.cvtColor(centers.reshape(1, 3, 3), cv2.COLOR_HSV2BGR)
        
        # Basic motion detection can be done by analyzing differences between frames
        # but that would require keeping track of previous frames
        
        # Extract textual descriptions using CLIP
        # We'll use a set of common visual concepts to get semantic features
        concepts = [
            "daytime", "nighttime", "indoor", "outdoor", "urban", "nature",
            "water", "person", "vehicle", "building", "animal", "text",
            "food", "technology", "bright", "dark", "colorful", "monochrome"
        ]
        
        text_inputs = self.clip_processor(text=concepts, return_tensors="pt", padding=True).to(self.device)
        
        with torch.no_grad():
            image_embeds = self.clip_model.get_image_features(**inputs)
            text_embeds = self.clip_model.get_text_features(**text_inputs)
            
            # Normalize embeddings
            image_embeds = image_embeds / image_embeds.norm(dim=-1, keepdim=True)
            text_embeds = text_embeds / text_embeds.norm(dim=-1, keepdim=True)
            
            # Calculate similarity scores
            similarity = (100.0 * image_embeds @ text_embeds.T).cpu().numpy()
        
        # Create dictionary of concept scores
        concept_scores = {concepts[i]: float(similarity[0][i]) for i in range(len(concepts))}
        
        # Package all features
        features = {
            'clip_embedding': image_features,
            'color_histogram': color_hist,
            'dominant_colors': dominant_colors.flatten(),
            'concept_scores': concept_scores
        }
        
        return features
    
    def serialize_features(self, features):
        """Serialize features for database storage."""
        return pickle.dumps(features)
    
    def deserialize_features(self, serialized_features):
        """Deserialize features from database."""
        return pickle.loads(serialized_features)
    
    def extract_segment_features(self, video_path, start_frame, end_frame, interval=None):
        """Extract features from a video segment.
        
        Args:
            video_path: Path to video file
            start_frame: Start frame number
            end_frame: End frame number
            interval: Frame interval for feature extraction (default: extract 5 frames)
            
        Returns:
            dict: Dictionary with feature vectors
        """
        if interval is None:
            # Calculate interval to extract 5 frames from the clip
            total_frames = end_frame - start_frame
            interval = max(1, total_frames // 5)
        
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            print(f"Error: Could not open video {video_path}")
            return None
            
        all_features = []
        sample_frames = list(range(start_frame, end_frame, interval))
        
        for frame_num in sample_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            if not ret:
                print(f"Error: Could not read frame {frame_num}")
                continue
                
            features = self.extract_frame_features(frame)
            all_features.append((frame_num, features))
            
        cap.release()
        
        # Combine features
        if not all_features:
            return None
            
        # Average CLIP embeddings
        clip_embeddings = np.stack([f[1]['clip_embedding'] for f in all_features])
        avg_clip_embedding = np.mean(clip_embeddings, axis=0)
        
        # Average color histograms
        color_hists = np.stack([f[1]['color_histogram'] for f in all_features])
        avg_color_hist = np.mean(color_hists, axis=0)
        
        # Average concept scores
        concepts = {}
        for _, features in all_features:
            for concept, score in features['concept_scores'].items():
                if concept not in concepts:
                    concepts[concept] = []
                concepts[concept].append(score)
        
        avg_concepts = {concept: np.mean(scores) for concept, scores in concepts.items()}
        
        # Create aggregate features
        aggregate_features = {
            'clip_embedding': avg_clip_embedding,
            'color_histogram': avg_color_hist,
            'concept_scores': avg_concepts,
            'frame_features': all_features,
            'frame_count': len(all_features)
        }
        
        return aggregate_features
    
    def compute_similarity(self, features1, features2, method='clip'):
        """Compute similarity between two feature sets.
        
        Args:
            features1: First feature set
            features2: Second feature set
            method: Similarity method ('clip', 'color', 'concepts', 'combined')
            
        Returns:
            float: Similarity score (0-1)
        """
        if method == 'clip':
            # Cosine similarity between CLIP embeddings
            sim = np.dot(features1['clip_embedding'], features2['clip_embedding'])
            return float(sim)
        
        elif method == 'color':
            # Histogram intersection for color histograms
            sim = cv2.compareHist(
                np.float32(features1['color_histogram']),
                np.float32(features2['color_histogram']),
                cv2.HISTCMP_INTERSECT
            )
            # Normalize to 0-1
            return float(sim / np.sum(features1['color_histogram']))
        
        elif method == 'concepts':
            # Average similarity of concept scores
            concepts1 = features1['concept_scores']
            concepts2 = features2['concept_scores']
            
            # Get common concepts
            common_concepts = set(concepts1.keys()) & set(concepts2.keys())
            if not common_concepts:
                return 0.0
                
            # Calculate difference for each concept and average
            diffs = [abs(concepts1[c] - concepts2[c]) for c in common_concepts]
            # Convert to similarity (0-1)
            return float(1.0 - np.mean(diffs) / 100.0)
        
        elif method == 'combined':
            # Weighted combination of all metrics
            clip_sim = self.compute_similarity(features1, features2, 'clip')
            color_sim = self.compute_similarity(features1, features2, 'color')
            concept_sim = self.compute_similarity(features1, features2, 'concepts')
            
            # Weighted average (give more weight to CLIP)
            return float(0.6 * clip_sim + 0.2 * color_sim + 0.2 * concept_sim)
        
        else:
            raise ValueError(f"Unknown similarity method: {method}")