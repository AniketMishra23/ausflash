// SectionTabs — horizontal scrollable pill tabs for filtering by section.
// Fixed height (48 px) prevents the ScrollView from stretching during loading.

import { View, ScrollView, TouchableOpacity, Text, StyleSheet } from 'react-native';
import { SECTIONS, SECTION_COLORS } from '@/constants/api';

interface Props {
  active:   string;                    // currently selected section label
  onChange: (section: string) => void; // called when user taps a tab
}

export default function SectionTabs({ active, onChange }: Props) {
  return (
    // Outer View constrains height so the ScrollView can't grow during loading
    <View style={styles.wrapper}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.container}
      >
        {SECTIONS.map(section => {
          const color    = SECTION_COLORS[section] ?? '#1D9E75';
          const isActive = section === active;
          return (
            <TouchableOpacity
              key={section}
              onPress={() => onChange(section)}
              style={[
                styles.tab,
                // Active tab: filled with section colour; inactive: outline only
                isActive
                  ? { backgroundColor: color, borderColor: color }
                  : { borderColor: color },
              ]}
              activeOpacity={0.75}
            >
              <Text style={[styles.label, { color: isActive ? '#fff' : color }]}>
                {section}
              </Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    height: 48,                          // fixed — prevents layout shift while loading
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  container: {
    paddingHorizontal: 12,
    alignItems: 'center',
    gap: 8,
    flexDirection: 'row',
    height: 48,
  },
  tab: {
    paddingHorizontal: 14,
    paddingVertical: 5,
    borderRadius: 20,
    borderWidth: 1.5,
  },
  label: {
    fontSize: 13,
    fontWeight: '600',
  },
});
