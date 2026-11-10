"""Unintegrated candidate: coalesce only adjacent, plain user message wrappers.

Content blocks remain byte-equivalent JSON values in the same order. This does
not trim history, add assistant/tool turns, change context policy, or guarantee
provider caching. Callers must explicitly remap any content-boundary indices.
"""
from copy import deepcopy
from dataclasses import dataclass


@dataclass(frozen=True)
class MessageBoundaryProjection:
    items: list
    original_item_indices: tuple
    original_content_coordinates: tuple

    def remap_content(self, message_index, content_index):
        """Locate an unchanged original block, e.g. a declared cache boundary."""
        if (type(message_index) is not int or type(content_index) is not int
                or message_index < 0 or content_index < 0):
            raise ValueError('Nonnegative original message/content indices required')
        try:
            return self.original_content_coordinates[message_index][content_index]
        except IndexError:
            raise ValueError('Original message/content boundary does not exist') from None


def _plain_user(item):
    return (isinstance(item, dict) and set(item) <= {'type', 'role', 'content'}
        and item.get('role') == 'user' and ('type' not in item or item['type'] == 'message')
        and isinstance(item.get('content'), list)
        and all(isinstance(block, dict) for block in item['content']))


def project_user_message_boundaries(items):
    """Return copied input plus exact original-block coordinates; never perform I/O.

    String content and messages with IDs, phases, names or other metadata are
    preserved as barriers. No role or tool-call boundary is crossed. Optional
    type='message' is an ordinary message wrapper, so it may share a user group.
    """
    if not isinstance(items, list):
        raise ValueError('A complete existing input-item list is required')
    output, indices, coordinates = [], [], []
    for original in items:
        copied = deepcopy(original)
        if output and _plain_user(original) and _plain_user(output[-1]):
            index, offset = len(output)-1, len(output[-1]['content'])
            output[-1]['content'].extend(copied['content'])
        else:
            index, offset = len(output), 0
            output.append(copied)
        content = original.get('content') if isinstance(original, dict) else None
        indices.append(index)
        coordinates.append(tuple((index, offset+i) for i in range(len(content)))
            if isinstance(content, list) else ())
    return MessageBoundaryProjection(output, tuple(indices), tuple(coordinates))


def coalesce_user_messages(items):
    """Candidate input list only; no mutation and no implicit runtime activation."""
    return project_user_message_boundaries(items).items
