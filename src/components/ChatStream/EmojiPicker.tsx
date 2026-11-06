import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Search,
  X,
  Clock,
  Smile,
  User,
  Leaf,
  Coffee,
  Trophy,
  Compass,
  Laptop,
  Heart,
} from 'lucide-react';
import {
  EMOJI_CATEGORIES,
  ALL_EMOJIS,
  EmojiItem,
  getRecentEmojis,
  saveRecentEmoji,
  searchEmojis,
} from './emojiData';
import './EmojiPicker.css';

interface EmojiPickerProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectEmoji: (emoji: string) => void;
}

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  recent: <Clock size={15} />,
  smileys: <Smile size={15} />,
  people: <User size={15} />,
  nature: <Leaf size={15} />,
  food: <Coffee size={15} />,
  activity: <Trophy size={15} />,
  travel: <Compass size={15} />,
  objects: <Laptop size={15} />,
  symbols: <Heart size={15} />,
};

export const EmojiPicker: React.FC<EmojiPickerProps> = ({
  isOpen,
  onClose,
  onSelectEmoji,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState<string>('smileys');
  const [recentEmojis, setRecentEmojis] = useState<string[]>([]);
  const [hoveredEmoji, setHoveredEmoji] = useState<EmojiItem | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  // Load recent emojis on open
  useEffect(() => {
    if (isOpen) {
      setRecentEmojis(getRecentEmojis());
      setTimeout(() => {
        searchInputRef.current?.focus();
      }, 50);
    } else {
      setSearchQuery('');
      setHoveredEmoji(null);
    }
  }, [isOpen]);

  // Handle outside click & escape key
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent | TouchEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        onClose();
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  // Filtered emojis based on search query
  const filteredEmojis = useMemo(() => {
    if (!searchQuery.trim()) return null;
    return searchEmojis(searchQuery);
  }, [searchQuery]);

  // Grouped emojis by category for normal browsing
  const groupedByCategory = useMemo(() => {
    const groups: Record<string, EmojiItem[]> = {};
    for (const cat of EMOJI_CATEGORIES) {
      if (cat.id !== 'recent') {
        groups[cat.id] = ALL_EMOJIS.filter((e) => e.category === cat.id);
      }
    }
    return groups;
  }, []);

  const handleSelect = (emojiChar: string, emojiItem?: EmojiItem) => {
    const updated = saveRecentEmoji(emojiChar);
    setRecentEmojis(updated);
    onSelectEmoji(emojiChar);
  };

  const scrollToCategory = (categoryId: string) => {
    setActiveCategory(categoryId);
    setSearchQuery('');

    if (scrollAreaRef.current) {
      const targetHeader = scrollAreaRef.current.querySelector(
        `[data-category-id="${categoryId}"]`
      );
      if (targetHeader) {
        targetHeader.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } else {
        scrollAreaRef.current.scrollTo({ top: 0, behavior: 'smooth' });
      }
    }
  };

  if (!isOpen) return null;

  return (
    <div
      ref={containerRef}
      className="emoji-picker-popover"
      role="dialog"
      aria-label="Emoji Picker"
      onClick={(e) => e.stopPropagation()}
    >
      {/* Header with Search and Clear */}
      <div className="emoji-picker-header">
        <div className="emoji-search-wrapper">
          <Search size={14} className="emoji-search-icon" />
          <input
            ref={searchInputRef}
            type="text"
            className="emoji-search-input"
            placeholder="Search emojis (e.g. smile, fire, robot)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button
              type="button"
              className="emoji-search-clear-btn"
              onClick={() => {
                setSearchQuery('');
                searchInputRef.current?.focus();
              }}
              title="Clear search"
            >
              <X size={12} />
            </button>
          )}
        </div>
        <button
          type="button"
          className="emoji-picker-close-btn"
          onClick={onClose}
          title="Close emoji picker (Esc)"
          aria-label="Close"
        >
          <X size={15} />
        </button>
      </div>

      {/* Category Tabs (shown when not searching) */}
      {!searchQuery && (
        <div className="emoji-category-tabs">
          {EMOJI_CATEGORIES.map((cat) => {
            const isActive = activeCategory === cat.id;
            return (
              <button
                key={cat.id}
                type="button"
                className={`emoji-category-tab ${isActive ? 'tab-active' : ''}`}
                onClick={() => scrollToCategory(cat.id)}
                title={cat.name}
                aria-label={cat.name}
              >
                {CATEGORY_ICONS[cat.id]}
              </button>
            );
          })}
        </div>
      )}

      {/* Emoji Scroll Area */}
      <div ref={scrollAreaRef} className="emoji-scroll-area">
        {filteredEmojis !== null ? (
          /* Search Results */
          <div className="emoji-search-results">
            <div className="emoji-category-title">
              Search Results ({filteredEmojis.length})
            </div>
            {filteredEmojis.length > 0 ? (
              <div className="emoji-grid">
                {filteredEmojis.map((item, idx) => (
                  <button
                    key={`${item.emoji}-${idx}`}
                    type="button"
                    className="emoji-item-btn"
                    title={item.name}
                    aria-label={item.name}
                    onMouseEnter={() => setHoveredEmoji(item)}
                    onMouseLeave={() => setHoveredEmoji(null)}
                    onClick={() => handleSelect(item.emoji, item)}
                  >
                    <span className="emoji-char">{item.emoji}</span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="emoji-empty-state">
                <span className="emoji-empty-icon">🔍</span>
                <p>No emojis found for "{searchQuery}"</p>
                <button
                  type="button"
                  className="emoji-clear-filter-btn"
                  onClick={() => setSearchQuery('')}
                >
                  Clear search
                </button>
              </div>
            )}
          </div>
        ) : (
          /* Normal Categorized Browse */
          <>
            {/* Recently Used Section */}
            {recentEmojis.length > 0 && (
              <div className="emoji-category-section" data-category-id="recent">
                <div className="emoji-category-title">
                  <Clock size={13} className="cat-header-icon" />
                  Recently Used
                </div>
                <div className="emoji-grid">
                  {recentEmojis.map((char, idx) => {
                    const matchedItem = ALL_EMOJIS.find((e) => e.emoji === char);
                    return (
                      <button
                        key={`recent-${char}-${idx}`}
                        type="button"
                        className="emoji-item-btn"
                        title={matchedItem?.name || char}
                        aria-label={matchedItem?.name || char}
                        onMouseEnter={() =>
                          setHoveredEmoji(
                            matchedItem || {
                              emoji: char,
                              name: 'Recent Emoji',
                              keywords: [],
                              category: 'recent',
                            }
                          )
                        }
                        onMouseLeave={() => setHoveredEmoji(null)}
                        onClick={() => handleSelect(char, matchedItem)}
                      >
                        <span className="emoji-char">{char}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* All Categories */}
            {EMOJI_CATEGORIES.filter((c) => c.id !== 'recent').map((cat) => {
              const list = groupedByCategory[cat.id] || [];
              if (list.length === 0) return null;

              return (
                <div
                  key={cat.id}
                  className="emoji-category-section"
                  data-category-id={cat.id}
                >
                  <div className="emoji-category-title">
                    {CATEGORY_ICONS[cat.id]}
                    <span>{cat.name}</span>
                  </div>
                  <div className="emoji-grid">
                    {list.map((item) => (
                      <button
                        key={item.emoji}
                        type="button"
                        className="emoji-item-btn"
                        title={item.name}
                        aria-label={item.name}
                        onMouseEnter={() => setHoveredEmoji(item)}
                        onMouseLeave={() => setHoveredEmoji(null)}
                        onClick={() => handleSelect(item.emoji, item)}
                      >
                        <span className="emoji-char">{item.emoji}</span>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </>
        )}
      </div>

      {/* Preview & Status Footer */}
      <div className="emoji-picker-footer">
        {hoveredEmoji ? (
          <div className="emoji-preview-box">
            <span className="emoji-preview-char">{hoveredEmoji.emoji}</span>
            <div className="emoji-preview-meta">
              <span className="emoji-preview-name">{hoveredEmoji.name}</span>
              <span className="emoji-preview-sub">
                {hoveredEmoji.category.toUpperCase()}
              </span>
            </div>
          </div>
        ) : (
          <div className="emoji-footer-hint">
            <span>✨ Click an emoji to insert into your chat message</span>
          </div>
        )}
      </div>
    </div>
  );
};
