import { View, ScrollView, TouchableOpacity, Text, StyleSheet } from 'react-native';
import { SECTIONS, SECTION_COLORS } from '@/constants/api';

interface Props {
  active:   string;
  onChange: (section: string) => void;
}

export default function SectionTabs({ active, onChange }: Props) {
  return (
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
    height: 48,
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
