// Feed screen — the main (and only visible) screen of AusFlash.
// Renders an InShorts-style vertical-paging card list.

import {
  View, FlatList, Text, ActivityIndicator,
  StyleSheet, Dimensions, StatusBar, RefreshControl,
} from 'react-native';
import { useState, useCallback } from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';
import SectionTabs from '@/components/SectionTabs';
import NewsCard from '@/components/NewsCard';
import { useFeed, Article } from '@/hooks/useFeed';

const { width } = Dimensions.get('window');

// ── Client-side deduplication ─────────────────────────────
// The API may return near-duplicate articles from different sources
// (e.g. ABC + Guardian both covering the same story).
// Normalise the first 8 words of each title and discard repeats.
function dedup(articles: Article[]): Article[] {
  const seen = new Set<string>();
  return articles.filter(a => {
    const key = a.title
      .toLowerCase()
      .replace(/[^a-z0-9 ]/g, '') // strip punctuation
      .split(' ')
      .slice(0, 8)                 // first 8 words is enough to detect same story
      .join(' ');
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// ── Ad placeholder ────────────────────────────────────────
// Shown every 5 articles. Replace the inner View with a real AdMob banner later.
function AdCard({ height }: { height: number }) {
  return (
    <View style={[styles.adCard, { height, width }]}>
      <View style={styles.adBox}>
        <Text style={styles.adLabel}>Advertisement</Text>
        <Text style={styles.adSub}>AdMob banner goes here</Text>
      </View>
    </View>
  );
}

// Injects an ad item into the feed list after every 5 real articles.
// Using a discriminated union (_type) so FlatList can tell cards from ads.
function injectAds(articles: Article[]) {
  const result: any[] = [];
  articles.forEach((article, i) => {
    result.push({ ...article, _type: 'article' });
    if ((i + 1) % 5 === 0) {
      result.push({ _type: 'ad', id: `ad-${i}` });
    }
  });
  return result;
}

// ── Screen ────────────────────────────────────────────────

export default function FeedScreen() {
  const [section, setSection]        = useState('All');
  const { articles, loading, error } = useFeed(section);
  const [refreshKey, setRefreshKey]  = useState(0);     // bump to force FlatList reset
  const [refreshing, setRefreshing]  = useState(false);
  const [cardHeight, setCardHeight]  = useState(0);     // measured on first render

  // Deduplicate then inject ads
  const clean = dedup(articles);
  const feed  = injectAds(clean);

  // Pull-to-refresh: bump refreshKey so FlatList remounts with fresh data
  const onRefresh = useCallback(() => {
    setRefreshing(true);
    setRefreshKey(k => k + 1);
    setTimeout(() => setRefreshing(false), 800);
  }, []);

  // renderItem is memoised so FlatList doesn't recreate it on every render
  const renderItem = useCallback(({ item, index }: { item: any; index: number }) => {
    if (!cardHeight) return null; // don't render until height is measured
    if (item._type === 'ad') return <AdCard height={cardHeight} />;
    // Compute the article's index within real articles only (ignoring ad items)
    const realIndex = feed.slice(0, index + 1).filter(i => i._type === 'article').length - 1;
    return <NewsCard article={item} index={realIndex} cardHeight={cardHeight} />;
  }, [feed, cardHeight]);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <StatusBar barStyle="dark-content" backgroundColor="#fff" />

      {/* ── Header ── */}
      <View style={styles.header}>
        <Text style={styles.logo}>
          Aus<Text style={styles.logoAccent}>Flash</Text>
        </Text>
        <Text style={styles.tagline}>Global news. Australian speed.</Text>
      </View>

      {/* ── Section filter tabs ── */}
      <SectionTabs active={section} onChange={setSection} />

      {/* ── Feed ─────────────────────────────────────────────
          onLayout measures the remaining height after header + tabs.
          This value is passed to each card so they fill the screen exactly. */}
      <View
        style={styles.feedContainer}
        onLayout={e => {
          const h = e.nativeEvent.layout.height;
          if (h > 0) setCardHeight(h);
        }}
      >
        {loading || cardHeight === 0 ? (
          <View style={styles.center}>
            <ActivityIndicator size="large" color="#1D9E75" />
            <Text style={styles.loadingText}>Loading news...</Text>
          </View>
        ) : error ? (
          <View style={styles.center}>
            <Text style={styles.errorText}>Could not load news.</Text>
            <Text style={styles.errorSub}>{error}</Text>
          </View>
        ) : clean.length === 0 ? (
          <View style={styles.center}>
            <Text style={styles.errorText}>No articles in this section yet.</Text>
          </View>
        ) : (
          <FlatList
            key={`${section}-${refreshKey}`}  // remount on section change or refresh
            data={feed}
            keyExtractor={(item, i) => item.id ?? `${item._type}-${i}`}
            renderItem={renderItem}
            pagingEnabled                      // snap one card at a time
            snapToInterval={cardHeight}
            snapToAlignment="start"
            decelerationRate="fast"
            showsVerticalScrollIndicator={false}
            // getItemLayout avoids expensive measure calls — all items are the same height
            getItemLayout={(_, index) => ({
              length: cardHeight,
              offset: cardHeight * index,
              index,
            })}
            refreshControl={
              <RefreshControl
                refreshing={refreshing}
                onRefresh={onRefresh}
                tintColor="#1D9E75"
              />
            }
          />
        )}
      </View>
    </SafeAreaView>
  );
}

// ── Styles ────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#fff',
  },
  header: {
    paddingHorizontal: 20,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  logo: {
    fontSize: 22,
    fontWeight: '900',
    color: '#111',
    letterSpacing: -0.5,
  },
  logoAccent: {
    color: '#1D9E75',
  },
  tagline: {
    fontSize: 11,
    color: '#999',
    fontStyle: 'italic',
  },
  feedContainer: {
    flex: 1, // takes all space below header + tabs
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
  },
  loadingText: {
    color: '#999',
    fontSize: 14,
    marginTop: 8,
  },
  errorText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
  },
  errorSub: {
    fontSize: 13,
    color: '#999',
  },
  adCard: {
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f9f9f9',
  },
  adBox: {
    width: '80%',
    height: 120,
    borderWidth: 1,
    borderColor: '#ddd',
    borderStyle: 'dashed',
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 6,
  },
  adLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#aaa',
  },
  adSub: {
    fontSize: 12,
    color: '#bbb',
  },
});
