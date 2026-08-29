"""Opt-in experimental descriptive audio analysis.

This module does not diagnose, assess truthfulness, or infer anxiety,
depression, instability, intent, or danger from a voice. Its output is never an
SPI feature and must never be the sole basis for an alert or other action.
Raw audio is processed only in a temporary file and is deleted immediately.
"""

import os
import tempfile

import numpy as np

from config import EXPERIMENTAL_AUDIO_LIMITATION, RAW_AUDIO_RETENTION_POLICY


def build_audio_analysis_metadata(
    *,
    opt_in=False,
    transcription_consent_recorded=False,
    consent_recorded=False,
    audio_quality="not_assessed",
    language="not_stated",
    device_limitations=None,
    model_uncertainty="high",
    analysis_status="not_requested",
    features=None,
    limitation=None,
):
    """Create a privacy-preserving metadata record without raw-audio content."""
    if any(type(value) is not bool for value in (opt_in, transcription_consent_recorded, consent_recorded)):
        raise ValueError("Audio opt-in, transcription consent, and audio-analysis consent must be booleans.")
    if not isinstance(device_limitations, list) or not all(isinstance(item, str) for item in device_limitations):
        raise ValueError("Audio device limitations must be a list of short labels.")
    if model_uncertainty not in {"low", "medium", "high", "not_assessed"}:
        raise ValueError("Audio model uncertainty must be low, medium, high, or not assessed.")
    return {
        "analysis_status": analysis_status,
        "experimental_opt_in": opt_in,
        "transcription_consent_recorded": transcription_consent_recorded,
        "consent_recorded": consent_recorded,
        "audio_quality": audio_quality or "not_assessed",
        "language": language or "not_stated",
        "device_limitations": device_limitations,
        "model_uncertainty": model_uncertainty,
        "raw_audio_retention_status": "discarded_after_transcription",
        "raw_audio_retention_policy": RAW_AUDIO_RETENTION_POLICY,
        "features": features or {},
        "limitation_notice": limitation or EXPERIMENTAL_AUDIO_LIMITATION,
        "not_used_for_alerts_or_spi": True,
    }


def extract_acoustic_features(
    audio_path,
    *,
    opt_in=False,
    transcription_consent_recorded=False,
    consent_recorded=False,
    audio_quality="not_assessed",
    language="not_stated",
    device_limitations=None,
    model_uncertainty="high",
):
    """Run opt-in descriptive analysis, returning metadata rather than an interpretation.

    With opt-in or consent absent, no model is invoked. Numeric descriptors, if
    available, remain opaque experimental metadata; they are not mapped to a
    mental state, credibility, or safety conclusion.
    """
    metadata = build_audio_analysis_metadata(
        opt_in=opt_in,
        transcription_consent_recorded=transcription_consent_recorded,
        consent_recorded=consent_recorded,
        audio_quality=audio_quality,
        language=language,
        device_limitations=device_limitations or [],
        model_uncertainty=model_uncertainty,
        analysis_status="not_requested",
    )
    if not opt_in:
        metadata["limitation_notice"] = "Experimental audio analysis was not requested. " + EXPERIMENTAL_AUDIO_LIMITATION
        return metadata
    if not consent_recorded:
        metadata["analysis_status"] = "blocked_missing_specific_consent"
        metadata["limitation_notice"] = "Experimental audio analysis was not run because specific consent was not recorded."
        return metadata
    try:
        import opensmile

        smile = opensmile.Smile(
            feature_set=opensmile.FeatureSet.eGeMAPSv02,
            feature_level=opensmile.FeatureLevel.Functionals,
        )
        features_df = smile.process_file(audio_path)
        if features_df.empty:
            metadata["analysis_status"] = "unavailable_no_usable_audio"
            return metadata
        metadata["analysis_status"] = "completed_experimental"
        metadata["features"] = {
            key: float(value) if not (np.isnan(value) or np.isinf(value)) else 0.0
            for key, value in features_df.iloc[0].to_dict().items()
        }
        return metadata
    except ImportError:
        metadata["analysis_status"] = "unavailable_model_not_installed"
        return metadata
    except Exception:
        metadata["analysis_status"] = "unavailable_processing_error"
        return metadata


def extract_acoustic_features_from_bytes(audio_bytes, filename="audio.wav", **kwargs):
    """Analyse an in-memory upload and delete its temporary raw-audio copy immediately."""
    if not isinstance(audio_bytes, (bytes, bytearray)):
        raise ValueError("Audio bytes are required for opt-in experimental analysis.")
    # Do not write raw bytes to disk merely to record that analysis is disabled
    # or blocked for missing consent.
    if kwargs.get("opt_in") is not True or kwargs.get("consent_recorded") is not True:
        return extract_acoustic_features("", **kwargs)
    suffix = os.path.splitext(filename or "audio.wav")[1] or ".wav"
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary_file:
            temporary_file.write(audio_bytes)
            temporary_path = temporary_file.name
        return extract_acoustic_features(temporary_path, **kwargs)
    finally:
        if temporary_path:
            try:
                os.remove(temporary_path)
            except FileNotFoundError:
                pass


def get_acoustic_feature_summary(metadata):
    """Return an experimental, non-clinical status statement only."""
    if not isinstance(metadata, dict):
        return "No experimental audio-analysis metadata is available."
    return (
        f"Experimental audio-analysis status: {metadata.get('analysis_status', 'not available')}. "
        "It is non-diagnostic and is not used for alerts or SPI."
    )
