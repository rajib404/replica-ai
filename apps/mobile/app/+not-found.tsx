import { Link, Stack } from "expo-router";
import { Text, View } from "react-native";

export default function NotFound() {
  return (
    <>
      <Stack.Screen options={{ title: "Not Found" }} />
      <View className="flex-1 items-center justify-center bg-black gap-4">
        <Text className="text-white text-xl font-semibold">Page not found</Text>
        <Link href="/" className="text-brand text-base">
          Go home
        </Link>
      </View>
    </>
  );
}
