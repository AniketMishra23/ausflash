import {
  View, Text, TouchableOpacity, StyleSheet,
  Dimensions, Linking, Alert,
} from 'react-native';
import { Article } from '@/hooks/useFeed';
import { SECTION_COLORS } from '@/constants/api';

const { width } = Dimensions.get('window');

function timeAgo(publishedAt: string): string {
  if (!publishedAt) return '';
  try {
    const ms   = Date.now() - new Date(publishedAt).getTime();
    const mins = Math.floor(ms / 60000);
    if (mins < 1)  return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24)  return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  } catch {
    return '';
  }
}

function getSummary(article: Article): string {
  const summary = article.ai_summary?.trim() ?? '';
  const desc    = article.description?.trim() ?? '';
  // Use ai_summary only if it has at least 20 words
  if (summary.split(' ').length >= 20) return summary;
  if (desc.length > 0) {
    const words = desc.split(' ');
    return words.length > 60 ? words.slice(0, 60).join(' ') + '...' : desc;
  }
  return summary;
}

async function openArticle(url: string) {
  try {
    await Linking.openURL(url);
  } catch {
    Alert.alert('Could not open article');
  }
}

interface Props {
  article:    Article;
  index:      number;
  cardHeight: number;
}

export default function NewsCard({ article, index, cardHeight }: Props) {
  const color   = SECTION_COLORS[article.section] ?? '#1D9E75';
  const summary = getSummary(article);

  return (
    <View style={[styles.card, { height: cardHeight }]}>
      {/* Source + time */}
      <View style={styles.meta}>
        <View style={[styles.sourceBadge, { backgroundColor: color }]}>
          <Text style={styles.sourceText} numberOfLines={1}>{article.website_name}</Text>
        </View>
        <Text style={styles.time}>{timeAgo(article.published_at)}</Text>
      </View>

      {/* Section label */}
      <Text style={[styles.sectionLabel, { color }]}>{article.section.toUpperCase()}</Text>

      {/* Title */}
      <Text style={styles.title}>{article.title}</Text>

      {/* Divider */}
      <View style={[styles.divider, { backgroundColor: color }]} />

      {/* Summary */}
      <Text style={styles.summary}>{summary}</Text>

      {/* Read more */}
      <TouchableOpacity
        style={[styles.readMore, { borderColor: color }]}
        onPress={() => openArticle(article.url)}
        activeOpacity={0.75}
      >
        <Text style={[styles.readMoreText, { color }]}>Read full article →</Text>
      </TouchableOpacity>

      {/* Card counter */}
      <Text style={styles.counter}>{index + 1}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    width,
    backgroundColor: '#fff',
    paddingHorizontal: 24,
    paddingTop: 28,
    paddingBottom: 32,
    justifyContent: 'flex-start',
  },
  meta: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 14,
    gap: 10,
  },
  sourceBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 4,
    maxWidth: 180,
  },
  sourceText: {
    color: '#fff',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  time: {
    fontSize: 12,
    color: '#999',
  },
  sectionLabel: {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.5,
    marginBottom: 10,
  },
  title: {
    fontSize: 22,
    fontWeight: '800',
    color: '#111',
    lineHeight: 30,
    marginBottom: 14,
  },
  divider: {
    height: 3,
    width: 40,
    borderRadius: 2,
    marginBottom: 14,
  },
  summary: {
    fontSize: 16,
    color: '#444',
    lineHeight: 26,
    marginBottom: 28,
  },
  readMore: {
    alignSelf: 'flex-start',
    borderWidth: 1.5,
    borderRadius: 6,
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  readMoreText: {
    fontSize: 14,
    fontWeight: '600',
  },
  counter: {
    position: 'absolute',
    bottom: 14,
    right: 20,
    fontSize: 12,
    color: '#ccc',
  },
});
