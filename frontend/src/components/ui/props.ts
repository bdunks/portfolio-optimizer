export type DefinedProps<T extends object> = {
  [Key in keyof T]?: Exclude<T[Key], undefined>;
};

export function omitUndefinedProps<T extends object>(props: T): DefinedProps<T> {
  return Object.fromEntries(
    Object.entries(props).filter(([, value]) => value !== undefined),
  ) as DefinedProps<T>;
}
