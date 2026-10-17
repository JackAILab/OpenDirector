from PIL import Image

from harness.evaluators.image_transform import observe_transform


def test_image_transform_observation_reports_bounded_pixel_change(tmp_path):
    source = tmp_path / 'source.png'
    result = tmp_path / 'result.png'
    Image.new('RGB', (32, 24), 'black').save(source)
    Image.new('RGB', (24, 32), 'white').save(result)

    observation = observe_transform(source, result)

    assert observation['status'] == 'changed_observed'
    assert observation['source_dimensions'] == [32, 24]
    assert observation['result_dimensions'] == [24, 32]
    assert observation['sample_dimensions'] == [128, 128]
    assert observation['changed_pixel_ratio'] > 0
    assert observation['mean_absolute_error'] > 0
    assert observation['human_review_required'] is True
    assert observation['training_eligible'] is False
    assert 'source' not in observation and 'result' not in observation


def test_image_transform_observation_distinguishes_unchanged_and_decode_failure(tmp_path):
    source = tmp_path / 'source.png'
    result = tmp_path / 'result.png'
    Image.new('RGB', (16, 16), 'navy').save(source)
    source.replace(result)
    unchanged = observe_transform(result, result)
    assert unchanged['status'] == 'unchanged'
    assert unchanged['changed_pixel_ratio'] == 0

    broken = tmp_path / 'broken.png'
    broken.write_bytes(b'not an image')
    failed = observe_transform(result, broken)
    assert failed['status'] == 'decode_failed'
    assert failed['human_review_required'] is True
    assert failed['training_eligible'] is False
