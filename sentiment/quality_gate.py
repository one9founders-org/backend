import json
import logging

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = [
    'overall_score',
    'sentiment_label',
    'top_praises',
    'top_complaints',
    'red_flags',
    'one_line_summary'
]

VALID_LABELS = ['positive', 'mixed', 'negative', 'insufficient_data']

RED_FLAG_KEYWORDS = [
    'breach', 'shutdown', 'scam', 'lawsuit', 'privacy',
    'ban', 'leak', 'stolen', 'fraud', 'bankrupt', 'hacked',
    'exposed', 'violated', 'suspended', 'closed'
]

def check_json_valid(raw_output: str) -> dict:
    """Check 1. Is the JSON valid and complete?"""
    try:
        result = json.loads(raw_output)
    except json.JSONDecodeError:
        logger.warning("[Gate] JSON parse failed")
        return None

    for field in REQUIRED_FIELDS:
        if field not in result:
            logger.warning(f"[Gate] Missing required field: {field}")
            return None

    return result


def check_score_valid(result: dict) -> bool:
    """Check 2. Is the score between 0.0 and 1.0?"""
    score = result.get('overall_score')
    if score is None:
        return False
    if not isinstance(score, (int, float)):
        return False
    if score < 0.0 or score > 1.0:
        logger.warning(f"[Gate] Score out of range: {score}")
        return False
    return True


def check_and_fix_label(result: dict) -> dict:
    """Check 3. Does the label match the score? Auto fix if not."""
    score = result['overall_score']
    label = result['sentiment_label']

    if label == 'insufficient_data':
        return result

    if label not in VALID_LABELS:
        logger.warning(f"[Gate] Invalid label: {label}. Auto correcting.")
        result['was_corrected'] = True

    # Determine correct label from score
    if score <= 0.35:
        correct_label = 'negative'
    elif score <= 0.60:
        correct_label = 'mixed'
    else:
        correct_label = 'positive'

    if label != correct_label:
        logger.warning(f"[Gate] Label mismatch. Score {score} but label '{label}'. Correcting to '{correct_label}'")
        result['sentiment_label'] = correct_label
        result['was_corrected'] = True

    return result


def check_and_fix_phrases(result: dict) -> dict:
    """Check 4. Are praises and complaints meaningful?"""
    def is_valid_phrase(phrase):
        if not phrase or not isinstance(phrase, str):
            return False
        if len(phrase.strip()) < 6:
            return False
        if len(phrase.strip()) > 40:
            return False
        if len(phrase.strip().split()) < 2:
            return False
        return True

    original_praises = result.get('top_praises', [])
    original_complaints = result.get('top_complaints', [])

    result['top_praises'] = [p for p in original_praises if is_valid_phrase(p)]
    result['top_complaints'] = [c for c in original_complaints if is_valid_phrase(c)]

    if len(result['top_praises']) < len(original_praises):
        logger.warning("[Gate] Stripped invalid praise phrases")
        result['was_corrected'] = True

    if len(result['top_complaints']) < len(original_complaints):
        logger.warning("[Gate] Stripped invalid complaint phrases")
        result['was_corrected'] = True

    return result


def check_and_fix_red_flags(result: dict) -> dict:
    """Check 5. Are red flags genuinely serious?"""
    def is_valid_red_flag(flag):
        if not flag or not isinstance(flag, str):
            return False
        if len(flag.strip().split()) < 5:
            return False
        flag_lower = flag.lower()
        return any(keyword in flag_lower for keyword in RED_FLAG_KEYWORDS)

    original_flags = result.get('red_flags', [])
    result['red_flags'] = [f for f in original_flags if is_valid_red_flag(f)]

    if len(result['red_flags']) < len(original_flags):
        logger.warning("[Gate] Removed invalid red flags")
        result['was_corrected'] = True

    return result


def check_confidence(result: dict, source_count: int) -> dict:
    """Check 6. Is there enough source data to trust this?"""
    if source_count == 0 or source_count <= 2:
        result['confidence'] = 'none'
        result['sentiment_label'] = 'insufficient_data'
    elif source_count <= 7:
        result['confidence'] = 'low'
    elif source_count <= 20:
        result['confidence'] = 'medium'
    else:
        result['confidence'] = 'high'

    return result


def run_quality_gate(raw_output: str, source_count: int, tool_name: str) -> dict:
    """
    Master quality gate function.
    Runs all 6 checks and returns validated result.
    """
    logger.info(f"[Gate] Running quality gate for: {tool_name}")

    # Check 1. JSON valid and complete?
    result = check_json_valid(raw_output)
    if result is None:
        logger.error(f"[Gate] HARD FAIL. Invalid JSON for {tool_name}")
        return {
            'overall_score': None,
            'sentiment_label': 'insufficient_data',
            'confidence': 'none',
            'top_praises': [],
            'top_complaints': [],
            'red_flags': [],
            'one_line_summary': 'Analysis failed validation.',
            'was_corrected': True
        }

    result.setdefault('was_corrected', False)

    # Check 2. Score valid?
    if not check_score_valid(result):
        logger.error(f"[Gate] HARD FAIL. Invalid score for {tool_name}")
        result['sentiment_label'] = 'insufficient_data'
        result['confidence'] = 'none'
        result['was_corrected'] = True
        return result

    # Check 3. Label matches score?
    result = check_and_fix_label(result)

    # Check 4. Phrases meaningful?
    result = check_and_fix_phrases(result)

    # Check 5. Red flags genuine?
    result = check_and_fix_red_flags(result)

    # Check 6. Confidence level?
    result = check_confidence(result, source_count)

    if result.get('was_corrected'):
        logger.info(f"[Gate] CORRECTED PASS for {tool_name}")
    else:
        logger.info(f"[Gate] CLEAN PASS for {tool_name}")

    return result